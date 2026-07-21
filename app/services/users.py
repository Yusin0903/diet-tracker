"""會員相關的商業邏輯:邀請碼檢查、註冊、登入。"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Food, User
from app.security import create_token, hash_password, verify_password
from app.settings import SEED_FOODS, settings


def check_invite_code(code: str) -> bool:
    codes = settings.invite_codes
    if not codes:
        # 沒設定任何邀請碼 => 禁止註冊(避免無腦開放)。
        return False
    return code.strip() in codes


def register_user(username: str, password: str, invite_code: str, db: Session) -> dict:
    username = username.strip()
    if not username or len(username) < 2:
        raise HTTPException(status_code=400, detail="帳號至少 2 個字")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密碼至少 6 個字")
    if not check_invite_code(invite_code):
        raise HTTPException(status_code=403, detail="邀請碼無效")

    # 建立使用者 + seed 常用食物在同一個交易內,避免「有帳號但沒 seed」的半套狀態。
    existing = db.execute(select(User.id).where(User.username == username)).first()
    if existing:
        raise HTTPException(status_code=409, detail="帳號已被使用")

    user = User(
        username=username,
        password_hash=hash_password(password),
        invite_code=invite_code.strip(),
    )
    db.add(user)
    db.flush()  # 取得 user.id 供 seed foods 使用

    for food in SEED_FOODS:
        stmt = (
            pg_insert(Food)
            .values(
                user_id=user.id,
                name=food["name"],
                calories=food["calories"],
                protein_g=food["protein_g"],
            )
            .on_conflict_do_nothing(index_elements=[Food.user_id, Food.name])
        )
        db.execute(stmt)

    token = create_token(user.id, user.username)
    return {"token": token, "username": user.username}


def login_user(username: str, password: str, db: Session) -> dict:
    username = username.strip()
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    token = create_token(user.id, user.username)
    return {"token": token, "username": user.username}
