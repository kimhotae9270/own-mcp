# app/services/google_token_manager.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import requests
import psycopg2

from app.core.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from app.core.db import db_conn


GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
# 만료 2분 전부터는 “만료로 간주” (클럭 스큐/네트워크 고려)
EXPIRY_SKEW = timedelta(minutes=2)


@dataclass
class GoogleTokens:
    access_token: str
    refresh_token: str | None
    expiry: datetime | None


def _get_tokens_for_user(conn, user_id: int) -> GoogleTokens:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT access_token, refresh_token, expiry
            FROM oauth_accounts
            WHERE user_id=%s AND provider='google'
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Google account not connected for this user")

        access_token, refresh_token, expiry = row
        # psycopg2가 TIMESTAMPTZ를 datetime으로 반환 (tz-aware가 보통)
        return GoogleTokens(access_token=access_token, refresh_token=refresh_token, expiry=expiry)


def _needs_refresh(expiry: datetime | None) -> bool:
    if expiry is None:
        # expiry가 없으면 보수적으로 refresh 시도 or 그냥 사용.
        # 운영에서는 보통 refresh 시도하는 게 안전
        return True
    now = datetime.now(timezone.utc)
    return now >= (expiry - EXPIRY_SKEW)


def _refresh_access_token(refresh_token: str) -> tuple[str, datetime]:
    """
    refresh_token으로 새 access_token과 expiry(절대시간)를 만든다.
    """
    resp = requests.post(
        GOOGLE_TOKEN_ENDPOINT,
        data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=10,
    )
    if resp.status_code != 200:
        # 대표적으로 invalid_grant면 사용자가 권한을 철회했거나 refresh_token이 죽은 상태
        raise RuntimeError(f"Google token refresh failed: {resp.status_code} {resp.text}")

    data = resp.json()
    new_access_token = data["access_token"]
    expires_in = int(data.get("expires_in", 3600))
    new_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return new_access_token, new_expiry


def get_valid_google_access_token(user_id: int) -> str:
    """
    항상 '유효한' access_token을 보장해서 반환.
    - 필요하면 refresh 하고 DB도 갱신함.
    """
    with db_conn() as conn:
        tokens = _get_tokens_for_user(conn, user_id)

        if not _needs_refresh(tokens.expiry):
            return tokens.access_token

        if not tokens.refresh_token:
            # refresh_token이 없으면 자동 갱신 불가 → 재연동 필요
            raise RuntimeError("No refresh_token. User must re-connect Google.")

        # refresh 시도
        new_access_token, new_expiry = _refresh_access_token(tokens.refresh_token)

        # DB 업데이트
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE oauth_accounts
                SET access_token=%s,
                    expiry=%s,
                    updated_at=now()
                WHERE user_id=%s AND provider='google'
                """,
                (new_access_token, new_expiry, user_id),
            )

        return new_access_token
