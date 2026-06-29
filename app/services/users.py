"""會員相關的商業邏輯:邀請碼檢查、註冊、登入。"""
from fastapi import HTTPException

from app.db import get_cursor
from app.security import create_token, hash_password, verify_password
from app.settings import SEED_FOODS, settings


def check_invite_code(code: str) -> bool:
    codes = settings.invite_codes
    if not codes:
        # 沒設定任何邀請碼 => 禁止註冊(避免無腦開放)。
        return False
    return code.strip() in codes


def register_user(username: str, password: str, invite_code: str) -> dict:
    username = username.strip()
    if not username or len(username) < 2:
        raise HTTPException(status_code=400, detail="帳號至少 2 個字")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密碼至少 6 個字")
    if not check_invite_code(invite_code):
        raise HTTPException(status_code=403, detail="邀請碼無效")

    # 建立使用者 + seed 常用食物在同一個交易內,避免「有帳號但沒 seed」的半套狀態。
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
        for food in SEED_FOODS:
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
