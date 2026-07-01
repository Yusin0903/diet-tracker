"""運動記錄的 MET 熱量估算 + 月曆彙總(月曆打卡格點 + 連續天數)。"""
from datetime import date, datetime, time, timedelta

from app.db import get_cursor
from app.services.profile import get_profile

# MET(代謝當量)常數表:kcal = MET × 體重kg × 時長(小時)。
# 存後端常數,不查外部 API;記錄當下算好存入,體重之後改動不回溯歷史。
MET = {
    "running": 7.0,
    "strength": 5.0,
    "yoga": 2.5,
    "cycling": 7.0,
    "swimming": 6.0,
    "ball": 7.0,
    "walking": 3.5,
    "stretch": 2.5,
    "other": 4.0,
}
DEFAULT_WEIGHT_KG = 65.0  # 沒填體重(個人資料)時的估算基準


def estimate_calories(user_id: int, ex_type: str, duration_min: int) -> int:
    prof = get_profile(user_id)
    weight = float(prof["weight_kg"]) if prof and prof.get("weight_kg") else DEFAULT_WEIGHT_KG
    met = MET.get(ex_type, MET["other"])
    return round(met * weight * duration_min / 60)


def _month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def month_marks(user_id: int, year: int, month: int, tz) -> list[str]:
    """該月裡有記錄運動的日期(給月曆打點用)。"""
    start_date, end_date = _month_range(year, month)
    start = datetime.combine(start_date, time.min, tzinfo=tz)
    end = datetime.combine(end_date, time.min, tzinfo=tz)
    with get_cursor() as cur:
        cur.execute(
            "SELECT logged_at FROM exercises WHERE user_id = %s AND logged_at >= %s AND logged_at < %s",
            (user_id, start, end),
        )
        rows = cur.fetchall()
    days = {r["logged_at"].astimezone(tz).date().isoformat() for r in rows}
    return sorted(days)


def compute_streak(user_id: int, tz, lookback_days: int = 400) -> int:
    """連續天數:從今天(沒記錄則從昨天)往回算,中斷就停。"""
    today = datetime.now(tz).date()
    start = datetime.combine(today - timedelta(days=lookback_days), time.min, tzinfo=tz)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz)
    with get_cursor() as cur:
        cur.execute(
            "SELECT logged_at FROM exercises WHERE user_id = %s AND logged_at >= %s AND logged_at < %s",
            (user_id, start, end),
        )
        rows = cur.fetchall()
    days = {r["logged_at"].astimezone(tz).date() for r in rows}
    cursor = today if today in days else today - timedelta(days=1)
    if cursor not in days:
        return 0
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak
