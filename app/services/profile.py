"""每位會員的目標設定讀寫(供 summary 與 profile 路由共用)。"""
from typing import Optional

from app.db import get_cursor


def get_profile(user_id: int) -> Optional[dict]:
    """取得會員的目標設定;沒設定回 None(summary 會走「只顯示熱量」模式)。"""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM profiles WHERE user_id = %s", (user_id,))
        r = cur.fetchone()
    if r is None:
        return None
    return {
        "mode": r["mode"],
        "sex": r["sex"],
        "age": r["age"],
        "height_cm": float(r["height_cm"]) if r["height_cm"] is not None else None,
        "weight_kg": float(r["weight_kg"]) if r["weight_kg"] is not None else None,
        "body_fat_pct": float(r["body_fat_pct"]) if r["body_fat_pct"] is not None else None,
        "measured_bmr": r["measured_bmr"],
        "activity_level": r["activity_level"],
        "goal": r["goal"],
        "calorie_adjust": r["calorie_adjust"],
        "tdee": r["tdee"],
        "calories_min": r["calories_min"],
        "calories_max": r["calories_max"],
        "protein_min": r["protein_min"],
    }


def save_profile(user_id: int, data: dict, result: dict) -> None:
    """寫入(upsert)會員的身體數據與算出的目標。"""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO profiles (
                user_id, mode, sex, age, height_cm, weight_kg, body_fat_pct,
                measured_bmr, activity_level, goal, calorie_adjust,
                tdee, calories_min, calories_max, protein_min, updated_at
            ) VALUES (
                %(user_id)s, %(mode)s, %(sex)s, %(age)s, %(height_cm)s, %(weight_kg)s,
                %(body_fat_pct)s, %(measured_bmr)s, %(activity_level)s, %(goal)s,
                %(calorie_adjust)s, %(tdee)s, %(calories_min)s, %(calories_max)s,
                %(protein_min)s, now()
            )
            ON CONFLICT (user_id) DO UPDATE SET
                mode = EXCLUDED.mode, sex = EXCLUDED.sex, age = EXCLUDED.age,
                height_cm = EXCLUDED.height_cm, weight_kg = EXCLUDED.weight_kg,
                body_fat_pct = EXCLUDED.body_fat_pct, measured_bmr = EXCLUDED.measured_bmr,
                activity_level = EXCLUDED.activity_level, goal = EXCLUDED.goal,
                calorie_adjust = EXCLUDED.calorie_adjust, tdee = EXCLUDED.tdee,
                calories_min = EXCLUDED.calories_min, calories_max = EXCLUDED.calories_max,
                protein_min = EXCLUDED.protein_min, updated_at = now()
            """,
            {
                "user_id": user_id,
                "mode": data.get("mode") or "auto",
                "sex": data.get("sex"),
                "age": data.get("age"),
                "height_cm": data.get("height_cm"),
                "weight_kg": data.get("weight_kg"),
                "body_fat_pct": data.get("body_fat_pct"),
                "measured_bmr": data.get("measured_bmr"),
                "activity_level": data.get("activity_level"),
                "goal": data.get("goal"),
                "calorie_adjust": result.get("calorie_adjust"),
                "tdee": result.get("tdee"),
                "calories_min": result["calories_min"],
                "calories_max": result["calories_max"],
                "protein_min": result["protein_min"],
            },
        )
