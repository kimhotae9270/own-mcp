import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException,Request, Response
from app.core.db import db_conn
import jwt
from app.services.google_oauth import make_flow, fetch_userinfo
from app.core.config import GOOGLE_SCOPES
from fastapi.responses import RedirectResponse
from app.core.config import JWT_SECRET, JWT_ALG
from app.core.security import (
    issue_access_jwt, issue_refresh_jwt,
    store_refresh_jti,
    ACCESS_COOKIE, REFRESH_COOKIE,
    verify_refresh_and_consume,
    revoke_user_refresh_tokens,
)

router = APIRouter(tags=["auth"])

STATE_TTL_MINUTES = 5
FRONTEND_URL = "http://localhost:3000"  # 너 프론트 주소
COOKIE_SECURE = False                  # 배포 HTTPS면 True
COOKIE_SAMESITE = "lax"

def _create_state_in_db(state: str, code_verifier: str) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MINUTES)
    with db_conn() as conn:
        with conn.cursor() as cur:
            # 만료된 state 정리 (가볍게)
            cur.execute("DELETE FROM oauth_states WHERE expires_at < now()")
            cur.execute(
                "INSERT INTO oauth_states(state, code_verifier, expires_at) VALUES (%s, %s, %s)",
                (state, code_verifier, expires_at),
            )

def _consume_state_from_db(state: str) -> str:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM oauth_states
                WHERE state=%s AND expires_at >= now()
                RETURNING code_verifier
                """,
                (state,),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                raise HTTPException(status_code=400, detail="Invalid or expired state")
            return row[0]


@router.get("/auth/google/login")
def google_login():
    state = secrets.token_urlsafe(32)

    flow = make_flow(state=state, use_pkce=True)

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
    )

    code_verifier = flow.code_verifier
    _create_state_in_db(state, code_verifier)

    return RedirectResponse(auth_url)


@router.get("/oauth/callback")
def oauth_callback(code: str, state: str):
    # 1) state 검증(공격 방지)
    code_verifier  = _consume_state_from_db(state)

    # 2) code -> token 교환
    flow = make_flow(state=state, use_pkce=False)
    flow.code_verifier = code_verifier
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
    access = issue_access_jwt(user_id)

    jti = secrets.token_urlsafe(32)
    refresh_exp = datetime.now(timezone.utc) + timedelta(days=14)
    store_refresh_jti(user_id=user_id, jti=jti, expires_at=refresh_exp)
    refresh = issue_refresh_jwt(user_id, jti)

    resp = RedirectResponse(url=f"{FRONTEND_URL}/oauth/success")

    resp.set_cookie(
        key=ACCESS_COOKIE,
        value=access,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=60 * 30,
        path="/",
    )

    # ✅ refresh는 refresh endpoint로만 보내게 path 제한(권장)
    resp.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=60 * 60 * 24 * 14,
        path="/auth/refresh",
    )

    return resp

@router.post("/auth/refresh")
def refresh_access_token(request: Request, response: Response):
    refresh = request.cookies.get(REFRESH_COOKIE)
    if not refresh:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    # 1) JWT 서명/exp 검증
    payload = jwt.decode(refresh, JWT_SECRET, algorithms=[JWT_ALG])
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    jti = payload.get("jti")
    if not jti:
        raise HTTPException(status_code=401, detail="Missing jti")

    # 2) DB에서 jti 유효성 확인 + 소비(회전: 한번 쓰면 revoked)
    user_id = verify_refresh_and_consume(jti)

    # 3) 새 access + 새 refresh 발급(회전)
    new_access = issue_access_jwt(user_id)

    new_jti = secrets.token_urlsafe(32)
    refresh_exp = datetime.now(timezone.utc) + timedelta(days=14)
    store_refresh_jti(user_id=user_id, jti=new_jti, expires_at=refresh_exp)
    new_refresh = issue_refresh_jwt(user_id, new_jti)

    response.set_cookie(
        key=ACCESS_COOKIE,
        value=new_access,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=60 * 30,
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=new_refresh,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=60 * 60 * 24 * 14,
        path="/auth/refresh",
    )
    return {"ok": True}

@router.post("/auth/logout")
def logout(request: Request, response: Response, user_id: int = None):
    # access가 살아있으면 user_id를 얻어서 해당 유저 refresh 전부 폐기(권장)
    try:
        # access 쿠키로부터 uid 가져오는 함수를 쓰면 더 좋음
        from app.core.security import get_current_user_id
        user_id = get_current_user_id(request)
        revoke_user_refresh_tokens(user_id)
    except Exception:
        pass

    response.delete_cookie(key=ACCESS_COOKIE, path="/")
    response.delete_cookie(key=REFRESH_COOKIE, path="/auth/refresh")
    return {"ok": True}
