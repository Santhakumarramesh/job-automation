from fastapi import Depends, HTTPException

class User:
    def __init__(self, user_id: str):
        self.id = user_id

def get_current_user():
    # Replace with real auth (OAuth2/JWT/session) in the future
    return User(user_id="demo-user")
