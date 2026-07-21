"""當日攝取加總 + 對照目標(summary 路由與好友動態共用)。"""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Entry
from app.services.profile import get_profile


def day_summary(user_id: int, start: datetime, end: datetime, db: Session) -> dict:
    agg = db.execute(
        select(
            func.coalesce(func.sum(Entry.calories), 0),
            func.coalesce(func.sum(Entry.protein_g), 0),
        ).where(Entry.user_id == user_id, Entry.eaten_at >= start, Entry.eaten_at < end)
    ).one()

    consumed_cal = int(agg[0])
    consumed_pro = float(agg[1])
    consumed = {"calories": consumed_cal, "protein_g": round(consumed_pro, 1)}

    prof = get_profile(user_id, db)
    if prof is None:
        return {
            "has_profile": False,
            "consumed": consumed,
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
        "has_profile": True,
        "consumed": consumed,
        "targets": {"calories_min": cmin, "calories_max": cmax, "protein_min": pmin, "tdee": tdee},
        "cap": cap,
        "remaining": {
            "calories_to_min": max(0, cmin - consumed_cal),
            "calories_to_tdee": (tdee - consumed_cal) if tdee else None,
            "protein_to_min": round(max(0, pmin - consumed_pro), 1),
        },
        "status": {"calories": cal_status, "protein": pro_status, "tdee": tdee_status},
    }


def mascot_only(ds: dict) -> dict:
    """從 day_summary 萃取「熊狀態」(顏色 + 水位比例),不外洩實際數字。"""
    if not ds["has_profile"]:
        return {"has_profile": False, "state": "blue", "fraction": 0.4}
    st = ds["status"]
    if st["tdee"] == "over":
        state = "red"
    elif st["calories"] == "in_range":
        state = "green"
    elif st["calories"] == "over":
        state = "amber"
    else:
        state = "blue"
    cap = ds["cap"] or 1
    fraction = round(ds["consumed"]["calories"] / cap, 3)
    return {"has_profile": True, "state": state, "fraction": fraction}
