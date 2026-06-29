"""當日加總 + 對照目標。

有 profile:回 TDEE / cap 與 tdee within/over 狀態(吉祥物用)。
沒 profile:不評估,只回當日攝取量。
"""
from typing import Optional

from fastapi import APIRouter, Depends

from app.db import get_cursor
from app.deps import day_bounds, resolve_tz
from app.security import current_user
from app.services.profile import get_profile

router = APIRouter(prefix="/api", tags=["summary"])


@router.get("/summary")
def summary(
    date: Optional[str] = None,
    tz: Optional[str] = None,
    user: dict = Depends(current_user),
):
    start, end, day_str = day_bounds(date, resolve_tz(tz))
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(calories), 0) AS calories,
                   COALESCE(SUM(protein_g), 0) AS protein_g
            FROM entries
            WHERE user_id = %s AND eaten_at >= %s AND eaten_at < %s
            """,
            (user["id"], start, end),
        )
        agg = cur.fetchone()

    consumed_cal = int(agg["calories"])
    consumed_pro = float(agg["protein_g"])
    consumed = {"calories": consumed_cal, "protein_g": round(consumed_pro, 1)}

    prof = get_profile(user["id"])

    # 沒設定身體數據:不評估目標,前端只顯示熱量數字。
    if prof is None:
        return {
            "date": day_str,
            "consumed": consumed,
            "has_profile": False,
            "targets": None,
            "cap": None,
            "remaining": None,
            "status": None,
        }

    cmin, cmax, pmin, tdee = (
        prof["calories_min"], prof["calories_max"], prof["protein_min"], prof["tdee"],
    )
    cap = tdee or cmax  # 吉祥物「滿格」基準:有 TDEE 用 TDEE,否則用熱量上限

    if consumed_cal < cmin:
        cal_status = "under"
    elif consumed_cal > cmax:
        cal_status = "over"
    else:
        cal_status = "in_range"
    pro_status = "met" if consumed_pro >= pmin else "short"
    tdee_status = "over" if (tdee and consumed_cal > tdee) else "within"

    return {
        "date": day_str,
        "consumed": consumed,
        "has_profile": True,
        "targets": {
            "calories_min": cmin,
            "calories_max": cmax,
            "protein_min": pmin,
            "tdee": tdee,
        },
        "cap": cap,
        "remaining": {
            "calories_to_min": max(0, cmin - consumed_cal),
            "calories_to_tdee": (tdee - consumed_cal) if tdee else None,
            "protein_to_min": round(max(0, pmin - consumed_pro), 1),
        },
        "status": {
            "calories": cal_status,
            "protein": pro_status,
            "tdee": tdee_status,
        },
    }
