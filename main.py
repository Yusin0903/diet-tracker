"""飲控 App 後端入口。

FastAPI + Postgres + Gemini vision,並 serve PWA 靜態檔。
所有飲食資料皆以登入會員(JWT)為界,且依台北時區計算「今天」。
"""
import os
from datetime import datetime, time, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
from auth import current_user, login_user, register_user
from database import get_cursor, init_pool
from gemini import analyze_food_image

app = FastAPI(title="飲控 App")

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")


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
def api_register(body: RegisterIn):
    return register_user(body.username, body.password, body.invite_code)


@app.post("/api/auth/login")
def api_login(body: LoginIn):
    return login_user(body.username, body.password)


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
    t = config.TARGETS

    if consumed_cal < t["calories_min"]:
        cal_status = "under"
    elif consumed_cal > t["calories_max"]:
        cal_status = "over"
    else:
        cal_status = "in_range"

    pro_status = "met" if consumed_pro >= t["protein_min"] else "short"

    return {
        "date": day_str,
        "consumed": {"calories": consumed_cal, "protein_g": round(consumed_pro, 1)},
        "targets": {
            "calories_min": t["calories_min"],
            "calories_max": t["calories_max"],
            "protein_min": t["protein_min"],
        },
        "remaining": {
            "calories_to_min": max(0, t["calories_min"] - consumed_cal),
            "protein_to_min": round(max(0, t["protein_min"] - consumed_pro), 1),
        },
        "status": {"calories": cal_status, "protein": pro_status},
    }


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


# ========================================================================
# PWA 靜態檔(放最後,避免蓋掉 /api 路由)
# ========================================================================
@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
