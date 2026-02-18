import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException,Request, Response, Depends
from app.core.security import get_current_user_id
from app.core.db import db_conn

from app.services.google_oauth import make_flow, fetch_userinfo
from app.core.config import GOOGLE_SCOPES
from fastapi.responses import RedirectResponse
from app.core.security import (
    issue_access_jwt, issue_refresh_jwt,
    store_refresh_jti,
    ACCESS_COOKIE, REFRESH_COOKIE,
    verify_refresh_and_consume,
    revoke_user_refresh_tokens,
    verify_refresh_token,
    REFRESH_EXPIRE_DAYS
)

router = APIRouter(tags=["auth"])

STATE_TTL_MINUTES = 5
FRONTEND_URL = "http://localhost:5173"  # 너 프론트 주소
COOKIE_SECURE = False                  # 배포 HTTPS면 True
COOKIE_SAMESITE = "lax"

async def _create_state_in_db(state: str, code_verifier: str) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MINUTES)

    async with db_conn() as conn:
        # 만료된 state 정리 (가볍게)
        await conn.execute("DELETE FROM oauth_states WHERE expires_at < now()")

        await conn.execute(
            """
            INSERT INTO oauth_states(state, code_verifier, expires_at)
            VALUES ($1, $2, $3)
            """,
            state, code_verifier, expires_at
        )


async def _consume_state_from_db(state: str) -> str:
    async with db_conn() as conn:
        row = await conn.fetchrow(
            """
            DELETE FROM oauth_states
            WHERE state=$1 AND expires_at >= now()
            RETURNING code_verifier
            """,
            state
        )

    if not row or not row["code_verifier"]:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    return row["code_verifier"]



@router.get("/auth/google/login")
async def google_login():
    state = secrets.token_urlsafe(32)

    flow = make_flow(state=state, use_pkce=True)

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
    )

    code_verifier = flow.code_verifier
    await _create_state_in_db(state, code_verifier)

    return RedirectResponse(auth_url)


@router.get("/oauth/callback")
async def oauth_callback(code: str, state: str):
    # 1) state 검증(공격 방지)
    code_verifier = await _consume_state_from_db(state)

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

    # 4) DB 저장 (asyncpg)
    async with db_conn() as conn:
        async with conn.transaction():
            # (A) 이미 이 google_sub가 연결된 user가 있는지 확인
            row = await conn.fetchrow(
                """
                SELECT user_id
                FROM oauth_accounts
                WHERE provider='google' AND provider_user_id=$1
                """,
                google_sub
            )

            if row:
                user_id = row["user_id"]
                # users 테이블의 email/name도 최신으로 갱신(선택)
                await conn.execute(
                    "UPDATE users SET email=$1, name=$2 WHERE id=$3",
                    email, name, user_id
                )
            else:
                # (B) 없다면 새 내부 유저 생성
                user_id = await conn.fetchval(
                    "INSERT INTO users(email, name) VALUES ($1, $2) RETURNING id",
                    email, name
                )

            # (C) oauth_accounts upsert
            expiry = getattr(creds, "expiry", None)  # datetime or None
            refresh_token = getattr(creds, "refresh_token", None)

            await conn.execute(
                """
                INSERT INTO oauth_accounts (
                    user_id, provider, provider_user_id,
                    access_token, refresh_token, expiry, scope
                )
                VALUES ($1, 'google', $2, $3, $4, $5, $6)
                ON CONFLICT (provider, provider_user_id)
                DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    access_token = EXCLUDED.access_token,
                    refresh_token = COALESCE(EXCLUDED.refresh_token, oauth_accounts.refresh_token),
                    expiry = EXCLUDED.expiry,
                    scope = EXCLUDED.scope,
                    updated_at = now()
                """,
                user_id,
                google_sub,
                creds.token,
                refresh_token,
                expiry,
                " ".join(GOOGLE_SCOPES),
            )

    # 5) 내부 JWT 발급(이제부터 우리 서비스 인증은 이 토큰으로)
    access = issue_access_jwt(user_id)

    jti = secrets.token_urlsafe(32)
    refresh_exp = datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRE_DAYS)
    await store_refresh_jti(user_id=user_id, jti=jti, expires_at=refresh_exp)
    refresh = issue_refresh_jwt(user_id, jti)

    resp = RedirectResponse(url=f"{FRONTEND_URL}/", status_code=303)

    resp.set_cookie(
        key=ACCESS_COOKIE,
        value=access,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=60 * 30,
        path="/",
    )

    resp.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=60 * 60 * 24 * REFRESH_EXPIRE_DAYS,
        path="/auth/refresh",
    )

    return resp




@router.post("/auth/refresh")
async def refresh_access_token(request: Request, response: Response):
    refresh = request.cookies.get(REFRESH_COOKIE)
    if not refresh:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    # 1) refresh JWT 검증 (type/jti)
    payload = verify_refresh_token(refresh)
    old_jti = payload["jti"]

    # 2) DB에서 old_jti 유효 확인 + 소비(회전)
    user_id = await verify_refresh_and_consume(old_jti)

    # 3) 새 access 발급
    new_access = issue_access_jwt(user_id)

    # 4) 새 refresh 발급
    now = datetime.now(timezone.utc)
    new_refresh_exp = now + timedelta(days=REFRESH_EXPIRE_DAYS)

    new_jti = secrets.token_urlsafe(32)
    await store_refresh_jti(user_id=user_id, jti=new_jti, expires_at=new_refresh_exp)
    new_refresh = issue_refresh_jwt(user_id, new_jti)

    # 5) 쿠키 세팅
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
        max_age=int((new_refresh_exp - now).total_seconds()),
        path="/auth/refresh",
    )
    return {"ok": True}

@router.post("/auth/logout")
async def logout(request: Request, response: Response, user_id: int = None):
    try:
        from app.core.security import get_current_user_id
        user_id = get_current_user_id(request)
        await revoke_user_refresh_tokens(user_id)
    except Exception:
        pass

    response.delete_cookie(key=ACCESS_COOKIE, path="/")
    response.delete_cookie(key=REFRESH_COOKIE, path="/auth/refresh")
    return {"ok": True}


@router.get("/auth/me")
async def me(user_id: int = Depends(get_current_user_id)):
    return {"ok": True, "user_id": user_id}
