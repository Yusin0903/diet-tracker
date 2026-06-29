"""每日目標計算:從使用者規格 / 體脂測量結果估 TDEE 與熱量、蛋白目標。

兩種輸入:
- 'auto' :填規格 → 估 BMR×活動係數 = TDEE → 依目標(減脂/維持/增肌)算熱量區間。
           有體脂率 → 用 Katch-McArdle(以淨體重 LBM 估,較準),蛋白也用 LBM 算。
           測量報告若直接給 BMR(measured_bmr)→ 直接採用,最準。
- 'manual':使用者已知自己的目標,直接給 calories_min/max、protein_min。

回傳一律含三個欄位:calories_min / calories_max / protein_min,summary 直接拿來用。
"""
from __future__ import annotations


class TargetError(ValueError):
    """輸入不足以計算目標時拋出,端點轉成 HTTP 400。"""


# 活動係數(TDEE = BMR × factor)
ACTIVITY_FACTORS = {
    "sedentary": 1.2,    # 久坐,幾乎不運動
    "light": 1.375,      # 輕度,每週運動 1-3 天
    "moderate": 1.55,    # 中度,每週 3-5 天
    "active": 1.725,     # 高度,每週 6-7 天
    "very_active": 1.9,  # 非常高,體力工作 / 一天兩練
}

# 依目標對 TDEE 的熱量調整(kcal)
GOAL_CALORIE_ADJUST = {"cut": -400, "maintain": 0, "bulk": 250}

# 蛋白目標(無體脂時用體重)g / kg 體重
GOAL_PROTEIN_PER_KG = {"cut": 2.0, "maintain": 1.8, "bulk": 1.8}

# 有體脂時用淨體重(LBM)g / kg LBM
PROTEIN_PER_KG_LBM = 2.4

CALORIE_BAND = 100  # 目標熱量上下各 ±100 形成區間


def _round_to(value: float, step: int) -> int:
    return int(round(value / step) * step)


def compute_auto(p: dict) -> dict:
    """從規格 / 體脂結果估算目標。p 為各輸入欄位的 dict。"""
    weight = _num(p.get("weight_kg"), "體重")
    if weight <= 0:
        raise TargetError("體重需大於 0")

    goal = p.get("goal") or "cut"
    if goal not in GOAL_CALORIE_ADJUST:
        raise TargetError("目標需為 cut / maintain / bulk")

    activity = p.get("activity_level") or "moderate"
    if activity not in ACTIVITY_FACTORS:
        raise TargetError("活動量不合法")

    bf = p.get("body_fat_pct")
    lbm = None
    if bf is not None:
        bf = float(bf)
        if not 3 <= bf <= 70:
            raise TargetError("體脂率需在 3–70% 之間")
        lbm = weight * (1 - bf / 100)

    # --- BMR ---
    measured_bmr = p.get("measured_bmr")
    if measured_bmr:
        if float(measured_bmr) <= 0:
            raise TargetError("量測 BMR 需大於 0")
        bmr = float(measured_bmr)
        method = "measured"          # 測量報告直接給 BMR,最準
    elif lbm is not None:
        bmr = 370 + 21.6 * lbm       # Katch-McArdle(需體脂)
        method = "katch"
    else:
        # Mifflin-St Jeor(需性別/年齡/身高/體重)
        sex = (p.get("sex") or "").lower()
        age = p.get("age")
        height = p.get("height_cm")
        if sex not in ("male", "female") or not age or not height:
            raise TargetError(
                "沒有體脂或量測 BMR 時,需填性別、年齡、身高、體重才能估算"
            )
        if int(age) <= 0 or float(height) <= 0:
            raise TargetError("年齡與身高需大於 0")
        base = 10 * weight + 6.25 * float(height) - 5 * int(age)
        bmr = base + (5 if sex == "male" else -161)
        method = "mifflin"

    tdee = bmr * ACTIVITY_FACTORS[activity]

    # --- 熱量目標 ---
    adjust = p.get("calorie_adjust")
    adjust = int(adjust) if adjust is not None else GOAL_CALORIE_ADJUST[goal]
    goal_cal = _round_to(tdee + adjust, 10)
    calories_min = goal_cal - CALORIE_BAND
    calories_max = goal_cal + CALORIE_BAND

    # --- 蛋白目標 ---
    if lbm is not None:
        protein_min = _round_to(lbm * PROTEIN_PER_KG_LBM, 5)
    else:
        protein_min = _round_to(weight * GOAL_PROTEIN_PER_KG[goal], 5)

    return {
        "method": method,
        "bmr": round(bmr),
        "tdee": round(tdee),
        "lbm": round(lbm, 1) if lbm is not None else None,
        "goal_calories": goal_cal,
        "calorie_adjust": adjust,
        "calories_min": calories_min,
        "calories_max": calories_max,
        "protein_min": protein_min,
    }


def validate_manual(p: dict) -> dict:
    """手動模式:直接採用使用者給的三個數字,做基本檢查。"""
    cmin = _num(p.get("calories_min"), "熱量下限")
    cmax = _num(p.get("calories_max"), "熱量上限")
    pmin = _num(p.get("protein_min"), "蛋白下限")
    if cmin <= 0 or cmax <= 0 or pmin <= 0:
        raise TargetError("目標需為正數")
    if cmin > cmax:
        raise TargetError("熱量下限不可大於上限")
    return {
        "method": "manual",
        "calories_min": int(cmin),
        "calories_max": int(cmax),
        "protein_min": int(pmin),
    }


def compute(p: dict) -> dict:
    """依 mode 分派。"""
    mode = p.get("mode") or "auto"
    if mode == "manual":
        return validate_manual(p)
    return compute_auto(p)


def _num(v, label: str) -> float:
    if v is None or v == "":
        raise TargetError(f"請填寫{label}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise TargetError(f"{label}需為數字")
