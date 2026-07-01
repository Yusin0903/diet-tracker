"""運動記錄:新增 / 查當日 / 查整月打卡狀態 / 刪除。"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_cursor
from app.deps import day_bounds, resolve_tz
from app.schemas import ExerciseIn
from app.security import current_user
from app.services.exercise import compute_streak, estimate_calories, month_marks

router = APIRouter(prefix="/api/exercises", tags=["exercises"])


def _serialize(r: dict, tz) -> dict:
    return {
        "id": r["id"],
        "logged_at": r["logged_at"].astimezone(tz).isoformat(),
        "ex_type": r["ex_type"],
        "duration_min": r["duration_min"],
        "distance_km": float(r["distance_km"]) if r["distance_km"] is not None else None,
        "calories": r["calories"],
        "note": r["note"],
    }


@router.post("")
def create_exercise(
    body: ExerciseIn, tz: Optional[str] = None, user: dict = Depends(current_user)
):
    zone = resolve_tz(tz)
    kcal = estimate_calories(user["id"], body.ex_type, body.duration_min)
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO exercises (user_id, ex_type, duration_min, distance_km, calories, note)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, logged_at, ex_type, duration_min, distance_km, calories, note
            """,
            (user["id"], body.ex_type, body.duration_min, body.distance_km, kcal, body.note),
        )
        row = cur.fetchone()
    return _serialize(row, zone)


@router.get("")
def list_exercises(
    date: Optional[str] = None, tz: Optional[str] = None, user: dict = Depends(current_user)
):
    zone = resolve_tz(tz)
    start, end, day_str = day_bounds(date, zone)
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, logged_at, ex_type, duration_min, distance_km, calories, note
            FROM exercises
            WHERE user_id = %s AND logged_at >= %s AND logged_at < %s
            ORDER BY logged_at DESC
            """,
            (user["id"], start, end),
        )
        rows = cur.fetchall()
    items = [_serialize(r, zone) for r in rows]
    return {
        "date": day_str,
        "items": items,
        "total_duration_min": sum(i["duration_min"] for i in items),
        "total_calories": sum(i["calories"] for i in items),
    }


@router.get("/month")
def month_calendar(
    year: int, month: int, tz: Optional[str] = None, user: dict = Depends(current_user)
):
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="month 需為 1–12")
    zone = resolve_tz(tz)
    return {
        "days": month_marks(user["id"], year, month, zone),
        "streak": compute_streak(user["id"], zone),
    }


@router.delete("/{exercise_id}")
def delete_exercise(exercise_id: int, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM exercises WHERE id = %s AND user_id = %s RETURNING id",
            (exercise_id, user["id"]),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到這筆記錄")
    return {"ok": True}
