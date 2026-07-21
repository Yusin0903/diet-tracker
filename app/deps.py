"""共用小工具:使用者時區解析與「今天」日界線計算。"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.settings import TAIPEI


def resolve_tz(tz_name: str | None) -> ZoneInfo:
    """把前端帶來的 IANA 時區字串轉成 ZoneInfo,無效則退回台北。"""
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001 (未知/無效時區字串)
            pass
    return TAIPEI


def day_bounds(date_str: str | None, tz: ZoneInfo) -> tuple[datetime, datetime, str]:
    """回傳某使用者時區自然日的 [起, 迄) UTC-aware 邊界,及該日字串。"""
    if date_str:
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式需為 YYYY-MM-DD")
    else:
        day = datetime.now(tz).date()
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start, end, day.isoformat()


def serialize_entry(e, tz: ZoneInfo = TAIPEI) -> dict:
    return {
        "id": e.id,
        "eaten_at": e.eaten_at.astimezone(tz).isoformat(),
        "name": e.name,
        "calories": e.calories,
        "protein_g": float(e.protein_g),
        "source": e.source,
        "note": e.note,
    }
