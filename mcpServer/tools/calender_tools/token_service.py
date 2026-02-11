from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

def get_google_creds(user_id: str):

    token = db.google_tokens.find_one({"user_id": user_id})

    creds = Credentials(
        token=token["access_token"],
        refresh_token=token["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=token["scopes"],
    )

    if creds.expired:
        creds.refresh(Request())

        db.google_tokens.update_one(
            {"user_id": user_id},
            {"$set": {"access_token": creds.token}}
        )

    return creds
