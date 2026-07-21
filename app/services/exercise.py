"""運動記錄的月曆彙總:該月哪幾天有記錄(打卡點)+ 連續天數。"""
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Exercise


def _month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def month_marks(user_id: int, year: int, month: int, tz, db: Session) -> list[str]:
    """該月裡有記錄運動的日期(給月曆打點用)。"""
    start_date, end_date = _month_range(year, month)
    start = datetime.combine(start_date, time.min, tzinfo=tz)
    end = datetime.combine(end_date, time.min, tzinfo=tz)
    rows = db.execute(
        select(Exercise.logged_at).where(
            Exercise.user_id == user_id, Exercise.logged_at >= start, Exercise.logged_at < end
        )
    ).scalars()
    days = {logged_at.astimezone(tz).date().isoformat() for logged_at in rows}
    return sorted(days)


def compute_streak(user_id: int, tz, db: Session, lookback_days: int = 400) -> int:
    """連續天數:從今天(沒記錄則從昨天)往回算,中斷就停。"""
    today = datetime.now(tz).date()
    start = datetime.combine(today - timedelta(days=lookback_days), time.min, tzinfo=tz)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz)
    rows = db.execute(
        select(Exercise.logged_at).where(
            Exercise.user_id == user_id, Exercise.logged_at >= start, Exercise.logged_at < end
        )
    ).scalars()
    days = {logged_at.astimezone(tz).date() for logged_at in rows}
    cursor = today if today in days else today - timedelta(days=1)
    if cursor not in days:
        return 0
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak
