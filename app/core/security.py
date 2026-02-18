# /mnt/data/security.py (개념상 app/core/security.py)

import jwt

from datetime import datetime, timedelta, timezone
from fastapi import Request, HTTPException

from app.core.config import JWT_SECRET, JWT_ALG
from app.core.db import db_conn

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"

ACCESS_EXPIRE_MINUTES = 30
REFRESH_EXPIRE_DAYS = 7


def issue_access_jwt(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "uid": user_id,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def issue_refresh_jwt(user_id: int, jti: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "uid": user_id,
        "jti": jti,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=REFRESH_EXPIRE_DAYS)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALG],
            options={"require": ["exp", "iat"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def store_refresh_jti(user_id: int, jti: str, expires_at: datetime) -> None:
    async with db_conn() as conn:
        await conn.execute(
            """
            INSERT INTO refresh_tokens (jti, user_id, expires_at)
            VALUES ($1, $2, $3)
            """,
            jti, user_id, expires_at
        )



async def verify_refresh_and_consume(jti: str) -> int:
    """
    refresh rotation 핵심:
    - jti가 DB에 있고 (revoked_at is null)
    - expires_at이 now()보다 미래면 OK
    - 그리고 즉시 revoked_at=now()로 바꿔서 "한 번 쓰면 폐기"
    """
    async with db_conn() as conn:
        row = await conn.fetchrow(
            """
            UPDATE refresh_tokens
            SET revoked_at = now()
            WHERE jti=$1
              AND revoked_at IS NULL
              AND expires_at > now()
            RETURNING user_id
            """,
            jti
        )

    if not row:
        raise HTTPException(status_code=401, detail="Refresh token invalid/revoked/expired")

    return int(row["user_id"])



async def revoke_user_refresh_tokens(user_id: int) -> None:
    async with db_conn() as conn:
        await conn.execute(
            """
            UPDATE refresh_tokens
            SET revoked_at = now()
            WHERE user_id=$1 AND revoked_at IS NULL
            """,
            user_id
        )


def get_current_user_id(request: Request) -> int:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")

    payload = _decode(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    uid = payload.get("uid")
    if uid is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return int(uid)

def verify_refresh_token(token: str) -> dict:
    payload = _decode(token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    if payload.get("uid") is None or payload.get("jti") is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token payload")

    return payload
