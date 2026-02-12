import jwt
from datetime import datetime, timedelta, timezone
from app.core.config import JWT_SECRET, JWT_ALG

def issue_internal_jwt(user_id: int, minutes: int = 60 * 24 * 7) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "uid": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
