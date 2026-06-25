"""密碼雜湊、JWT、以及取出目前登入者的 FastAPI 依賴。

- 密碼用 pbkdf2_hmac(stdlib,免額外原生套件)雜湊。
- 登入後發 JWT,前端帶 Authorization: Bearer <token>。
"""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.settings import settings

bearer = HTTPBearer(auto_error=False)
_PBKDF2_ROUNDS = 200_000


# --- 密碼雜湊 -----------------------------------------------------------
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds_s, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds_s)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# --- JWT ----------------------------------------------------------------
def create_token(user_id: int, username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": now,
        "exp": now + timedelta(days=settings.token_ttl_days),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="登入已過期,請重新登入")


# --- 依賴:取出目前登入者 ----------------------------------------------
def current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
) -> dict:
    if creds is None:
        raise HTTPException(status_code=401, detail="請先登入")
    payload = _decode_token(creds.credentials)
    return {"id": int(payload["sub"]), "username": payload.get("username", "")}
