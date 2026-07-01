"""運動記錄的熱量估算 + 月曆彙總(月曆打卡格點 + 連續天數)。

熱量估算優先用「配速」換算(有距離時):跑步/走路套 ACSM 步行與跑步能量公式,
單車套 compendium 的速度區間 MET;都比死板套一個固定 MET 準確,尤其配速偏慢時
(例如 20 分鐘走/跑 1 公里,時速僅 3km/h,實際上接近散步,不該套跑步的高 MET)。
沒填距離(或不適用速度的類型,如重訓/瑜伽)才退回固定 MET。
"""
from datetime import date, datetime, time, timedelta

from app.db import get_cursor
from app.services.profile import get_profile

# 固定 MET(代謝當量)常數表,沒有距離可換算配速時使用:kcal = MET × 體重kg × 時長(小時)。
# 存後端常數,不查外部 API;記錄當下算好存入,體重之後改動不回溯歷史。
MET = {
    "running": 7.0,   # 慢跑,沒填距離時的預設強度
    "strength": 5.0,
    "yoga": 2.5,
    "cycling": 7.0,   # 中等速度,沒填距離時的預設強度
    "swimming": 6.0,
    "ball": 7.0,
    "walking": 3.5,
    "stretch": 2.5,
    "other": 4.0,
}
DEFAULT_WEIGHT_KG = 65.0  # 沒填體重(個人資料)時的估算基準

# 配速門檻:低於這個時速,就算類型選「跑步」,實際上也是走路的步態與強度
# (compendium 裡最慢的「跑步」條目大約落在 4mph≈6.4km/h,再慢就不是跑了)。
RUNNING_MIN_SPEED_KMH = 6.4


def _ambulation_met(speed_kmh: float, ex_type: str) -> float:
    """ACSM 代謝當量公式(平地、無坡度):
    走路 VO2 = 0.1 × 速度(m/min) + 3.5;跑步 VO2 = 0.2 × 速度(m/min) + 3.5;MET = VO2 / 3.5。
    """
    speed_m_per_min = speed_kmh * 1000 / 60
    is_running = ex_type == "running" and speed_kmh >= RUNNING_MIN_SPEED_KMH
    vo2 = (0.2 if is_running else 0.1) * speed_m_per_min + 3.5
    return vo2 / 3.5


def _cycling_met(speed_kmh: float) -> float:
    """Compendium of Physical Activities 的單車速度區間 MET(平地、一般騎乘)。"""
    if speed_kmh < 16:
        return 4.0
    if speed_kmh < 19:
        return 6.8
    if speed_kmh < 22.4:
        return 8.0
    if speed_kmh < 25.6:
        return 10.0
    if speed_kmh < 30.6:
        return 12.0
    return 15.8


def _resolve_met(ex_type: str, duration_min: int, distance_km: float | None) -> float:
    if distance_km and distance_km > 0 and duration_min > 0:
        speed_kmh = distance_km / (duration_min / 60)
        if ex_type in ("running", "walking"):
            return _ambulation_met(speed_kmh, ex_type)
        if ex_type == "cycling":
            return _cycling_met(speed_kmh)
    return MET.get(ex_type, MET["other"])


def estimate_calories(
    user_id: int, ex_type: str, duration_min: int, distance_km: float | None = None
) -> int:
    prof = get_profile(user_id)
    weight = float(prof["weight_kg"]) if prof and prof.get("weight_kg") else DEFAULT_WEIGHT_KG
    met = _resolve_met(ex_type, duration_min, distance_km)
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
