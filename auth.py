"""會員認證:註冊(需邀請碼)、登入、JWT。

- 密碼用 pbkdf2_hmac(stdlib,免額外原生套件)雜湊。
- 邀請碼從環境變數 INVITE_CODES 讀,不在前端、不寫死在程式裡。
- 登入後發 JWT,前端帶 Authorization: Bearer <token>。
"""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import config
from database import get_cursor

_bearer = HTTPBearer(auto_error=False)

# --- 密碼雜湊 -----------------------------------------------------------
_PBKDF2_ROUNDS = 200_000


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
        "exp": now + timedelta(days=config.TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, config.SECRET_KEY, algorithm="HS256")


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="登入已過期,請重新登入")


# --- 邀請碼 -------------------------------------------------------------
def check_invite_code(code: str) -> bool:
    if not config.INVITE_CODES:
        # 沒設定任何邀請碼 => 禁止註冊(避免無腦開放)。
        return False
    return code.strip() in config.INVITE_CODES


# --- 註冊 / 登入 --------------------------------------------------------
def register_user(username: str, password: str, invite_code: str) -> dict:
    username = username.strip()
    if not username or len(username) < 2:
        raise HTTPException(status_code=400, detail="帳號至少 2 個字")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密碼至少 6 個字")
    if not check_invite_code(invite_code):
        raise HTTPException(status_code=403, detail="邀請碼無效")

    # 建立使用者 + seed 常用食物在同一個交易內,確保不會產生「有帳號但沒
    # seed」的半套狀態。
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="帳號已被使用")
        cur.execute(
            """
            INSERT INTO users (username, password_hash, invite_code)
            VALUES (%s, %s, %s) RETURNING id, username
            """,
            (username, hash_password(password), invite_code.strip()),
        )
        row = cur.fetchone()
        for food in config.SEED_FOODS:
            cur.execute(
                """
                INSERT INTO foods (user_id, name, calories, protein_g)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, name) DO NOTHING
                """,
                (row["id"], food["name"], food["calories"], food["protein_g"]),
            )

    token = create_token(row["id"], row["username"])
    return {"token": token, "username": row["username"]}


def login_user(username: str, password: str) -> dict:
    username = username.strip()
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, username, password_hash FROM users WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    token = create_token(row["id"], row["username"])
    return {"token": token, "username": row["username"]}


# --- 依賴:取出目前登入者 ----------------------------------------------
def current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    if creds is None:
        raise HTTPException(status_code=401, detail="請先登入")
    payload = _decode_token(creds.credentials)
    return {"id": int(payload["sub"]), "username": payload.get("username", "")}
