"""targets.py 的單元測試:TDEE / 熱量 / 蛋白估算與輸入驗證。"""
import pytest

from app.services import targets


# ---------- Mifflin-St Jeor ----------
def test_mifflin_male():
    r = targets.compute(
        {"mode": "auto", "sex": "male", "age": 30, "height_cm": 178,
         "weight_kg": 80, "activity_level": "moderate", "goal": "cut"}
    )
    assert r["method"] == "mifflin"
    # BMR = 10*80 + 6.25*178 - 5*30 + 5 = 1767.5 -> round 1768
    assert r["bmr"] == 1768
    # TDEE = 1768 * 1.55 = 2740.4 -> 2740
    assert r["tdee"] == 2740
    # cut: -400 -> 2340 round10 -> band ±100
    assert r["calories_min"] == 2240
    assert r["calories_max"] == 2440
    # protein cut 2.0/kg * 80 = 160
    assert r["protein_min"] == 160


def test_mifflin_female_differs():
    male = targets.compute({"mode": "auto", "sex": "male", "age": 30,
                            "height_cm": 170, "weight_kg": 70,
                            "activity_level": "light", "goal": "maintain"})
    female = targets.compute({"mode": "auto", "sex": "female", "age": 30,
                              "height_cm": 170, "weight_kg": 70,
                              "activity_level": "light", "goal": "maintain"})
    # 男女常數差 166 (+5 vs -161)
    assert male["bmr"] - female["bmr"] == 166


# ---------- Katch-McArdle(有體脂) ----------
def test_katch_uses_lbm():
    r = targets.compute(
        {"mode": "auto", "weight_kg": 80, "body_fat_pct": 18,
         "activity_level": "moderate", "goal": "cut"}
    )
    assert r["method"] == "katch"
    assert r["lbm"] == pytest.approx(65.6, abs=0.05)
    # BMR = 370 + 21.6*65.6 = 1786.96 -> 1787
    assert r["bmr"] == 1787
    # 蛋白用 LBM*2.4 = 157.4 -> round5 = 155
    assert r["protein_min"] == 155


def test_measured_bmr_takes_priority_over_katch():
    r = targets.compute(
        {"mode": "auto", "weight_kg": 80, "body_fat_pct": 18,
         "measured_bmr": 1750, "activity_level": "active", "goal": "maintain"}
    )
    assert r["method"] == "measured"
    # TDEE = 1750 * 1.725 = 3018.75 -> 3019
    assert r["tdee"] == 3019


# ---------- goal 調整 ----------
@pytest.mark.parametrize("goal,expected_adjust", [
    ("cut", -400), ("maintain", 0), ("bulk", 250),
])
def test_goal_calorie_adjust(goal, expected_adjust):
    r = targets.compute({"mode": "auto", "sex": "male", "age": 30,
                         "height_cm": 178, "weight_kg": 80,
                         "activity_level": "moderate", "goal": goal})
    assert r["calorie_adjust"] == expected_adjust


def test_calorie_adjust_override():
    r = targets.compute({"mode": "auto", "sex": "male", "age": 30,
                         "height_cm": 178, "weight_kg": 80,
                         "activity_level": "moderate", "goal": "cut",
                         "calorie_adjust": -250})
    assert r["calorie_adjust"] == -250
    # goal_calories = tdee - 250 within band
    assert r["calories_max"] - r["calories_min"] == 200


@pytest.mark.parametrize("activity,factor", [
    ("sedentary", 1.2), ("light", 1.375), ("moderate", 1.55),
    ("active", 1.725), ("very_active", 1.9),
])
def test_activity_factors(activity, factor):
    r = targets.compute({"mode": "auto", "sex": "male", "age": 30,
                         "height_cm": 178, "weight_kg": 80,
                         "activity_level": activity, "goal": "maintain"})
    # TDEE 由未取整的 BMR 乘活動係數而來,與顯示用的整數 BMR 容許 1 kcal 誤差
    assert abs(r["tdee"] - r["bmr"] * factor) <= 1.5


# ---------- manual ----------
def test_manual_passthrough():
    r = targets.compute({"mode": "manual", "calories_min": 1700,
                         "calories_max": 1900, "protein_min": 150})
    assert r == {"method": "manual", "calories_min": 1700,
                 "calories_max": 1900, "protein_min": 150}


def test_manual_rejects_min_gt_max():
    with pytest.raises(targets.TargetError):
        targets.compute({"mode": "manual", "calories_min": 2000,
                         "calories_max": 1900, "protein_min": 150})


def test_manual_rejects_missing():
    with pytest.raises(targets.TargetError):
        targets.compute({"mode": "manual", "calories_min": 1700,
                         "calories_max": 1900})  # 缺 protein_min


# ---------- 輸入驗證 ----------
def test_auto_requires_specs_without_bf_or_bmr():
    with pytest.raises(targets.TargetError):
        targets.compute({"mode": "auto", "weight_kg": 80,
                         "activity_level": "moderate", "goal": "cut"})


def test_rejects_nonpositive_age():
    with pytest.raises(targets.TargetError):
        targets.compute({"mode": "auto", "sex": "male", "age": -5,
                         "height_cm": 178, "weight_kg": 80,
                         "activity_level": "moderate", "goal": "cut"})


def test_rejects_bad_body_fat():
    with pytest.raises(targets.TargetError):
        targets.compute({"mode": "auto", "weight_kg": 80, "body_fat_pct": 95,
                         "activity_level": "moderate", "goal": "cut"})


def test_rejects_nonpositive_measured_bmr():
    with pytest.raises(targets.TargetError):
        targets.compute({"mode": "auto", "weight_kg": 80, "measured_bmr": -100,
                         "activity_level": "moderate", "goal": "cut"})


def test_rejects_missing_weight():
    with pytest.raises(targets.TargetError):
        targets.compute({"mode": "auto", "sex": "male", "age": 30,
                         "height_cm": 178, "activity_level": "moderate",
                         "goal": "cut"})


def test_rejects_bad_goal():
    with pytest.raises(targets.TargetError):
        targets.compute({"mode": "auto", "sex": "male", "age": 30,
                         "height_cm": 178, "weight_kg": 80,
                         "activity_level": "moderate", "goal": "bogus"})
