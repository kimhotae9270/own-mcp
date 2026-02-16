import os

DATABASE_URL = os.getenv("DATABASE_URL")  # Neon connection string
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
INTERNAL_JWT_SECRET = os.getenv("INTERNAL_JWT_SECRET")
INTERNAL_JWT_ISSUER = os.getenv("INTERNAL_JWT_ISSUER")
# 로컬 개발용. 배포 시 https 도메인으로 바꾸세요.
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

# 캘린더 이벤트 권한 (필요에 맞게 readonly/full 조절)
GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/calendar.events",
]

JWT_SECRET = os.getenv("JWT_SECRET")  # 절대 fallback 넣지 말 것
JWT_ALG = "HS256"

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")
if not GOOGLE_CLIENT_ID:
    raise RuntimeError("GOOGLE_CLIENT_ID is not set")
if not GOOGLE_CLIENT_SECRET:
    raise RuntimeError("GOOGLE_CLIENT_SECRET is not set")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET is not set")
