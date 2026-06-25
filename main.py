"""飲控 App 後端入口。

FastAPI + Postgres + Gemini vision,並 serve PWA 靜態檔。
所有飲食資料皆以登入會員(JWT)為界,且依台北時區計算「今天」。
"""
import os
from datetime import datetime, time, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
import targets
from auth import current_user, login_user, register_user
from database import get_cursor, init_pool
from gemini import analyze_food_image
from ratelimit import RateLimiter, client_ip

app = FastAPI(title="飲控 App")

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")

# per-IP 速率限制:擋邀請碼/密碼暴力嘗試
register_limiter = RateLimiter(
    config.REG_MAX_FAILURES, config.REG_WINDOW_S, config.REG_BLOCK_S
)
login_limiter = RateLimiter(
    config.LOGIN_MAX_FAILURES, config.LOGIN_WINDOW_S, config.LOGIN_BLOCK_S
)


@app.on_event("startup")
def _startup() -> None:
    init_pool()


# --- Pydantic models ----------------------------------------------------
class RegisterIn(BaseModel):
    username: str
    password: str
    invite_code: str


class LoginIn(BaseModel):
    username: str
    password: str


class EntryIn(BaseModel):
    name: str = Field(..., min_length=1)
    calories: int = Field(..., ge=0)
    protein_g: float = Field(..., ge=0)
    source: str = Field("manual")  # 'photo' | 'manual' | 'favorite'
    note: Optional[str] = None


class FoodIn(BaseModel):
    name: str = Field(..., min_length=1)
    calories: int = Field(..., ge=0)
    protein_g: float = Field(..., ge=0)


class ProfileIn(BaseModel):
    mode: str = "auto"  # 'auto' | 'manual'
    # auto 輸入
    sex: Optional[str] = None
    age: Optional[int] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    body_fat_pct: Optional[float] = None
    measured_bmr: Optional[int] = None
    activity_level: Optional[str] = None
    goal: Optional[str] = None
    calorie_adjust: Optional[int] = None
    # manual 直接輸入目標
    calories_min: Optional[int] = None
    calories_max: Optional[int] = None
    protein_min: Optional[int] = None


# --- 時區小工具 ---------------------------------------------------------
def _taipei_day_bounds(date_str: Optional[str]) -> tuple[datetime, datetime, str]:
    """回傳某台北自然日的 [起, 迄) UTC-aware 邊界,及該日字串。"""
    if date_str:
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式需為 YYYY-MM-DD")
    else:
        day = datetime.now(config.TAIPEI).date()
    start = datetime.combine(day, time.min, tzinfo=config.TAIPEI)
    end = start + timedelta(days=1)
    return start, end, day.isoformat()


# ========================================================================
# 認證
# ========================================================================
@app.post("/api/auth/register")
def api_register(body: RegisterIn, request: Request):
    ip = client_ip(request)
    register_limiter.check(ip)  # 已被鎖就直接 429
    try:
        result = register_user(body.username, body.password, body.invite_code)
    except HTTPException as e:
        # 只有「邀請碼錯」才算暴力嘗試,計一次失敗
        if e.status_code == 403:
            register_limiter.record_failure(ip)
        raise
    register_limiter.reset(ip)  # 成功註冊,清掉該 IP 的失敗計數
    return result


@app.post("/api/auth/login")
def api_login(body: LoginIn, request: Request):
    ip = client_ip(request)
    login_limiter.check(ip)
    try:
        result = login_user(body.username, body.password)
    except HTTPException as e:
        if e.status_code == 401:  # 帳密錯誤
            login_limiter.record_failure(ip)
        raise
    login_limiter.reset(ip)
    return result


@app.get("/api/auth/me")
def api_me(user: dict = Depends(current_user)):
    return {"username": user["username"]}


# ========================================================================
# Gemini 圖片分析(不寫 DB)
# ========================================================================
@app.post("/api/analyze")
async def api_analyze(
    file: UploadFile = File(...), user: dict = Depends(current_user)
):
    image_bytes = await file.read()
    try:
        result = analyze_food_image(image_bytes, file.content_type or "image/jpeg")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"分析失敗,請改用手動輸入:{e}")
    return result  # 等使用者確認後才呼叫 /api/entries 寫入


# ========================================================================
# 飲食記錄
# ========================================================================
@app.post("/api/entries")
def api_create_entry(body: EntryIn, user: dict = Depends(current_user)):
    if body.source not in ("photo", "manual", "favorite"):
        raise HTTPException(status_code=400, detail="source 不合法")
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO entries (user_id, name, calories, protein_g, source, note)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, eaten_at, name, calories, protein_g, source, note
            """,
            (user["id"], body.name, body.calories, body.protein_g, body.source, body.note),
        )
        row = cur.fetchone()
    return _serialize_entry(row)


@app.get("/api/entries")
def api_list_entries(
    date: Optional[str] = None, user: dict = Depends(current_user)
):
    start, end, _ = _taipei_day_bounds(date)
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, eaten_at, name, calories, protein_g, source, note
            FROM entries
            WHERE user_id = %s AND eaten_at >= %s AND eaten_at < %s
            ORDER BY eaten_at DESC
            """,
            (user["id"], start, end),
        )
        rows = cur.fetchall()
    return [_serialize_entry(r) for r in rows]


@app.delete("/api/entries/{entry_id}")
def api_delete_entry(entry_id: int, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM entries WHERE id = %s AND user_id = %s RETURNING id",
            (entry_id, user["id"]),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到這筆記錄")
    return {"ok": True}


# ========================================================================
# 當日加總 + 對照目標
# ========================================================================
@app.get("/api/summary")
def api_summary(date: Optional[str] = None, user: dict = Depends(current_user)):
    start, end, day_str = _taipei_day_bounds(date)
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

    prof = _get_profile(user["id"])

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

    cmin = prof["calories_min"]
    cmax = prof["calories_max"]
    pmin = prof["protein_min"]
    tdee = prof["tdee"]
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


# ========================================================================
# 每日目標 / 身體數據(每位會員各自的 TDEE 與目標)
# ========================================================================
@app.get("/api/profile")
def api_get_profile(user: dict = Depends(current_user)):
    prof = _get_profile(user["id"])
    return {"profile": prof}


@app.post("/api/profile/preview")
def api_preview_profile(body: ProfileIn, user: dict = Depends(current_user)):
    """只估算、不存檔,讓前端在儲存前先看 TDEE 與目標。"""
    try:
        return targets.compute(body.model_dump())
    except targets.TargetError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/profile")
def api_save_profile(body: ProfileIn, user: dict = Depends(current_user)):
    data = body.model_dump()
    try:
        result = targets.compute(data)
    except targets.TargetError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
                "user_id": user["id"],
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
    return {"saved": True, "result": result, "profile": _get_profile(user["id"])}


# ========================================================================
# 常用食物
# ========================================================================
@app.get("/api/foods")
def api_list_foods(user: dict = Depends(current_user)):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, name, calories, protein_g
            FROM foods WHERE user_id = %s ORDER BY name
            """,
            (user["id"],),
        )
        rows = cur.fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "calories": r["calories"],
            "protein_g": float(r["protein_g"]),
        }
        for r in rows
    ]


@app.post("/api/foods")
def api_create_food(body: FoodIn, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO foods (user_id, name, calories, protein_g)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, name)
            DO UPDATE SET calories = EXCLUDED.calories, protein_g = EXCLUDED.protein_g
            RETURNING id, name, calories, protein_g
            """,
            (user["id"], body.name, body.calories, body.protein_g),
        )
        r = cur.fetchone()
    return {
        "id": r["id"],
        "name": r["name"],
        "calories": r["calories"],
        "protein_g": float(r["protein_g"]),
    }


@app.delete("/api/foods/{food_id}")
def api_delete_food(food_id: int, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM foods WHERE id = %s AND user_id = %s RETURNING id",
            (food_id, user["id"]),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到這個食物")
    return {"ok": True}


# --- helpers ------------------------------------------------------------
def _serialize_entry(r: dict) -> dict:
    return {
        "id": r["id"],
        "eaten_at": r["eaten_at"].astimezone(config.TAIPEI).isoformat(),
        "name": r["name"],
        "calories": r["calories"],
        "protein_g": float(r["protein_g"]),
        "source": r["source"],
        "note": r["note"],
    }


def _get_profile(user_id: int) -> Optional[dict]:
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


# ========================================================================
# PWA 靜態檔(放最後,避免蓋掉 /api 路由)
# ========================================================================
@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
