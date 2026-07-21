"""認證:註冊(需邀請碼)、登入,並對兩者做 per-IP 速率限制。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.rate_limit import RateLimiter, client_ip
from app.schemas import LoginIn, RegisterIn
from app.security import current_user
from app.services.users import login_user, register_user
from app.settings import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

_register_limiter = RateLimiter(
    settings.reg_max_failures, settings.reg_window_s, settings.reg_block_s
)
_login_limiter = RateLimiter(
    settings.login_max_failures, settings.login_window_s, settings.login_block_s
)


@router.post("/register")
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    _register_limiter.check(ip)  # 已被鎖就直接 429
    try:
        result = register_user(body.username, body.password, body.invite_code, db)
    except HTTPException as e:
        if e.status_code == 403:  # 只有「邀請碼錯」算暴力嘗試
            _register_limiter.record_failure(ip)
        raise
    _register_limiter.reset(ip)  # 成功註冊,清掉該 IP 的失敗計數
    return result


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    _login_limiter.check(ip)
    try:
        result = login_user(body.username, body.password, db)
    except HTTPException as e:
        if e.status_code == 401:  # 帳密錯誤
            _login_limiter.record_failure(ip)
        raise
    _login_limiter.reset(ip)
    return result


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return {"username": user["username"]}
