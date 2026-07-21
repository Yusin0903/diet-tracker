"""每位會員的目標設定讀寫(供 summary 與 profile 路由共用)。"""
from typing import Optional

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Profile


def get_profile(user_id: int, db: Session) -> Optional[dict]:
    """取得會員的目標設定;沒設定回 None(summary 會走「只顯示熱量」模式)。"""
    p = db.get(Profile, user_id)
    if p is None:
        return None
    return {
        "mode": p.mode,
        "sex": p.sex,
        "age": p.age,
        "height_cm": float(p.height_cm) if p.height_cm is not None else None,
        "weight_kg": float(p.weight_kg) if p.weight_kg is not None else None,
        "body_fat_pct": float(p.body_fat_pct) if p.body_fat_pct is not None else None,
        "measured_bmr": p.measured_bmr,
        "activity_level": p.activity_level,
        "goal": p.goal,
        "calorie_adjust": p.calorie_adjust,
        "tdee": p.tdee,
        "calories_min": p.calories_min,
        "calories_max": p.calories_max,
        "protein_min": p.protein_min,
    }


def save_profile(user_id: int, data: dict, result: dict, db: Session) -> None:
    """寫入(upsert)會員的身體數據與算出的目標。"""
    values = dict(
        user_id=user_id,
        mode=data.get("mode") or "auto",
        sex=data.get("sex"),
        age=data.get("age"),
        height_cm=data.get("height_cm"),
        weight_kg=data.get("weight_kg"),
        body_fat_pct=data.get("body_fat_pct"),
        measured_bmr=data.get("measured_bmr"),
        activity_level=data.get("activity_level"),
        goal=data.get("goal"),
        calorie_adjust=result.get("calorie_adjust"),
        tdee=result.get("tdee"),
        calories_min=result["calories_min"],
        calories_max=result["calories_max"],
        protein_min=result["protein_min"],
        updated_at=func.now(),
    )
    stmt = pg_insert(Profile).values(**values)
    update_cols = {c: stmt.excluded[c] for c in values if c != "user_id"}
    stmt = stmt.on_conflict_do_update(index_elements=[Profile.user_id], set_=update_cols)
    db.execute(stmt)
