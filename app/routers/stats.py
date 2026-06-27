"""熱量趨勢:某日期區間內,每天的熱量/蛋白加總 + 目標上下限。"""
from datetime import datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_cursor
from app.deps import resolve_tz
from app.security import current_user
from app.services.profile import get_profile

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def stats(
    start: str,
    end: str,
    tz: Optional[str] = None,
    user: dict = Depends(current_user),
):
    zone = resolve_tz(tz)
    try:
        d0 = datetime.strptime(start, "%Y-%m-%d").date()
        d1 = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式需為 YYYY-MM-DD")
    if d1 < d0:
        raise HTTPException(status_code=400, detail="結束日不可早於起始日")
    if (d1 - d0).days > 366:
        raise HTTPException(status_code=400, detail="範圍過大")

    start_dt = datetime.combine(d0, time.min, tzinfo=zone)
    end_dt = datetime.combine(d1 + timedelta(days=1), time.min, tzinfo=zone)
    tzname = getattr(zone, "key", "Asia/Taipei")  # 給 SQL 用的 IANA 名稱

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT timezone(%s, eaten_at)::date AS day,
                   COALESCE(SUM(calories), 0) AS calories,
                   COALESCE(SUM(protein_g), 0) AS protein_g
            FROM entries
            WHERE user_id = %s AND eaten_at >= %s AND eaten_at < %s
            GROUP BY day
            """,
            (tzname, user["id"], start_dt, end_dt),
        )
        by_day = {
            r["day"].isoformat(): {
                "calories": int(r["calories"]),
                "protein_g": float(r["protein_g"]),
            }
            for r in cur.fetchall()
        }

    # 補滿區間內每一天(沒記錄的填 0),讓前端長條圖連續
    days = []
    cur_day = d0
    while cur_day <= d1:
        key = cur_day.isoformat()
        v = by_day.get(key, {"calories": 0, "protein_g": 0.0})
        days.append({"date": key, "calories": v["calories"], "protein_g": round(v["protein_g"], 1)})
        cur_day += timedelta(days=1)

    prof = get_profile(user["id"])
    targets = (
        {
            "calories_min": prof["calories_min"],
            "calories_max": prof["calories_max"],
            "tdee": prof["tdee"],
        }
        if prof
        else None
    )
    return {"days": days, "targets": targets}
