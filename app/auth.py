import os
from fastapi import Depends, HTTPException, Header

class User:
    def __init__(self, user_id: str):
        self.id = user_id


def get_current_user(x_api_key: str | None = Header(None)):
    """
    Auth: X-API-Key header (optional). If API_KEY env is set, require it.
    Fallback: demo-user when no API_KEY configured (local dev).
    """
    api_key = os.getenv("API_KEY", "")
    if not api_key:
        return User(user_id="demo-user")  # No key configured = local dev
    if not x_api_key or x_api_key != api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return User(user_id="api-key-user")
