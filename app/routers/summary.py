"""當日加總 + 對照目標。

有 profile:回 TDEE / cap 與 tdee within/over 狀態(吉祥物用)。
沒 profile:不評估,只回當日攝取量。
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import day_bounds, resolve_tz
from app.security import current_user
from app.services.summary import day_summary

router = APIRouter(prefix="/api", tags=["summary"])


@router.get("/summary")
def summary(
    date: Optional[str] = None,
    tz: Optional[str] = None,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    start, end, day_str = day_bounds(date, resolve_tz(tz))
    return {"date": day_str, **day_summary(user["id"], start, end, db)}
