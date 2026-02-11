# app/routers/auth.py

import os
from fastapi import APIRouter
from google_auth_oauthlib.flow import Flow
from dotenv import load_dotenv


load_dotenv()
router = APIRouter(
    tags=["auth"]
)

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events"
]

REDIRECT_URI = "http://localhost:9000/oauth/callback"


@router.get("/auth/google/login")
def google_login():
    print(CLIENT_ID)

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    auth_url, state = flow.authorization_url(
        access_type="offline",   # ⭐ refresh_token 받기
        prompt="consent"
    )

    return {"auth_url": auth_url}


@router.get("/oauth/callback")
async def oauth_callback(code: str):

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    flow.fetch_token(code=code)

    creds = flow.credentials

    # TODO: user 정보 조회 + DB 저장
    # save_google_token(...)

    return {"status": "google connected"}
