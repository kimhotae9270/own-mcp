import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from app.core.db import db_conn
from app.core.security import issue_internal_jwt
from app.services.google_oauth import make_flow, fetch_userinfo
from app.core.config import GOOGLE_SCOPES
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["auth"])

STATE_TTL_MINUTES = 5


def _create_state_in_db(state: str) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MINUTES)
    with db_conn() as conn:
        with conn.cursor() as cur:
            # 만료된 state 정리 (가볍게)
            cur.execute("DELETE FROM oauth_states WHERE expires_at < now()")
            cur.execute(
                "INSERT INTO oauth_states(state, expires_at) VALUES (%s, %s)",
                (state, expires_at),
            )


def _consume_state_from_db(state: str) -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            # 있으면 지우면서 검증(재사용 방지)
            cur.execute(
                "DELETE FROM oauth_states WHERE state=%s AND expires_at >= now() RETURNING state",
                (state,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="Invalid or expired state")


@router.get("/auth/google/login")
def google_login():
    state = secrets.token_urlsafe(32)
    _create_state_in_db(state)

    flow = make_flow(state=state)
    auth_url, _ = flow.authorization_url(
        access_type="offline",     # refresh_token 요청
        prompt="consent",          # refresh_token 재발급 유도(처음 연결/권한변경 등)
        include_granted_scopes="true",
    )

    return RedirectResponse(auth_url)


@router.get("/oauth/callback")
def oauth_callback(code: str, state: str):
    # 1) state 검증(공격 방지)
    _consume_state_from_db(state)

    # 2) code -> token 교환
    flow = make_flow(state=state)
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch token: {e}")

    creds = flow.credentials
    if not creds or not creds.token:
        raise HTTPException(status_code=400, detail="No access token returned")

    # 3) userinfo로 google sub/email/name 확보
    try:
        userinfo = fetch_userinfo(creds.token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch userinfo: {e}")

    google_sub = userinfo.get("sub")
    email = userinfo.get("email")
    name = userinfo.get("name")

    if not google_sub:
        raise HTTPException(status_code=400, detail="Google user 'sub' not found")

    # 4) DB 저장:
    #   - users: 내부 유저 생성/조회 (여기서는 email/name은 참고정보)
    #   - oauth_accounts: (provider, provider_user_id=sub) 기준 upsert
    with db_conn() as conn:
        with conn.cursor() as cur:
            # (A) 이미 이 google_sub가 연결된 user가 있는지 확인
            cur.execute(
                """
                SELECT user_id
                FROM oauth_accounts
                WHERE provider='google' AND provider_user_id=%s
                """,
                (google_sub,),
            )
            row = cur.fetchone()

            if row:
                user_id = row[0]
                # users 테이블의 email/name도 최신으로 갱신(선택)
                cur.execute(
                    "UPDATE users SET email=%s, name=%s WHERE id=%s",
                    (email, name, user_id),
                )
            else:
                # (B) 없다면 새 내부 유저 생성
                cur.execute(
                    "INSERT INTO users(email, name) VALUES (%s, %s) RETURNING id",
                    (email, name),
                )
                user_id = cur.fetchone()[0]

            # (C) oauth_accounts upsert
            expiry = getattr(creds, "expiry", None)  # datetime or None
            refresh_token = getattr(creds, "refresh_token", None)

            cur.execute(
                """
                INSERT INTO oauth_accounts (
                    user_id, provider, provider_user_id,
                    access_token, refresh_token, expiry, scope
                )
                VALUES (%s, 'google', %s, %s, %s, %s, %s)
                ON CONFLICT (provider, provider_user_id)
                DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    access_token = EXCLUDED.access_token,
                    refresh_token = COALESCE(EXCLUDED.refresh_token, oauth_accounts.refresh_token),
                    expiry = EXCLUDED.expiry,
                    scope = EXCLUDED.scope,
                    updated_at = now()
                """,
                (
                    user_id,
                    google_sub,
                    creds.token,
                    refresh_token,
                    expiry,
                    " ".join(GOOGLE_SCOPES),
                ),
            )

    # 5) 내부 JWT 발급(이제부터 우리 서비스 인증은 이 토큰으로)
    internal_jwt = issue_internal_jwt(user_id)

    return {
        "status": "google connected",
        "user": {"id": user_id, "email": email, "name": name, "google_sub": google_sub},
        "access_token": internal_jwt,
        "token_type": "bearer",
    }
