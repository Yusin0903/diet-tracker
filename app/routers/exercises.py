"""運動記錄:新增 / 查當日 / 查整月打卡狀態 / 刪除,以及重訓的動作與組數細節。"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_cursor
from app.deps import day_bounds, resolve_tz
from app.schemas import ExerciseIn, MovementIn, SetIn
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
    kcal = estimate_calories(user["id"], body.ex_type, body.duration_min, body.distance_km)
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


# ---------- 重訓明細:動作 + 組數(熱量仍用「重訓 MET × 時長」,這裡只存訓練內容) ----------
def _serialize_set(s: dict) -> dict:
    return {
        "id": s["id"],
        "weight_kg": float(s["weight_kg"]) if s["weight_kg"] is not None else None,
        "reps": s["reps"],
    }


def _require_owned_exercise(exercise_id: int, user_id: int) -> None:
    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM exercises WHERE id = %s AND user_id = %s", (exercise_id, user_id))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到這筆運動記錄")


@router.get("/{exercise_id}/movements")
def list_movements(exercise_id: int, user: dict = Depends(current_user)):
    _require_owned_exercise(exercise_id, user["id"])
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name FROM exercise_movements WHERE exercise_id = %s ORDER BY sort_order, id",
            (exercise_id,),
        )
        movements = cur.fetchall()
        result = []
        for m in movements:
            cur.execute(
                "SELECT id, weight_kg, reps FROM exercise_sets WHERE movement_id = %s ORDER BY set_order, id",
                (m["id"],),
            )
            result.append({
                "id": m["id"], "name": m["name"],
                "sets": [_serialize_set(s) for s in cur.fetchall()],
            })
    return result


@router.post("/{exercise_id}/movements")
def add_movement(exercise_id: int, body: MovementIn, user: dict = Depends(current_user)):
    _require_owned_exercise(exercise_id, user["id"])
    with get_cursor(commit=True) as cur:
        cur.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next FROM exercise_movements WHERE exercise_id = %s",
            (exercise_id,),
        )
        next_order = cur.fetchone()["next"]
        cur.execute(
            "INSERT INTO exercise_movements (exercise_id, name, sort_order) VALUES (%s, %s, %s) RETURNING id, name",
            (exercise_id, body.name, next_order),
        )
        row = cur.fetchone()
    return {"id": row["id"], "name": row["name"], "sets": []}


@router.delete("/movements/{movement_id}")
def delete_movement(movement_id: int, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            DELETE FROM exercise_movements m USING exercises e
            WHERE m.id = %s AND m.exercise_id = e.id AND e.user_id = %s
            RETURNING m.id
            """,
            (movement_id, user["id"]),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到這個動作")
    return {"ok": True}


@router.post("/movements/{movement_id}/sets")
def add_set(movement_id: int, body: SetIn, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT m.id FROM exercise_movements m JOIN exercises e ON e.id = m.exercise_id
            WHERE m.id = %s AND e.user_id = %s
            """,
            (movement_id, user["id"]),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到這個動作")
        cur.execute(
            "SELECT COALESCE(MAX(set_order), -1) + 1 AS next FROM exercise_sets WHERE movement_id = %s",
            (movement_id,),
        )
        next_order = cur.fetchone()["next"]
        cur.execute(
            """
            INSERT INTO exercise_sets (movement_id, set_order, weight_kg, reps)
            VALUES (%s, %s, %s, %s) RETURNING id, weight_kg, reps
            """,
            (movement_id, next_order, body.weight_kg, body.reps),
        )
        row = cur.fetchone()
    return _serialize_set(row)


@router.put("/sets/{set_id}")
def edit_set(set_id: int, body: SetIn, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE exercise_sets s SET weight_kg = %s, reps = %s
            FROM exercise_movements m, exercises e
            WHERE s.id = %s AND s.movement_id = m.id AND m.exercise_id = e.id AND e.user_id = %s
            RETURNING s.id, s.weight_kg, s.reps
            """,
            (body.weight_kg, body.reps, set_id, user["id"]),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="找不到這組紀錄")
    return _serialize_set(row)


@router.delete("/sets/{set_id}")
def delete_set(set_id: int, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            DELETE FROM exercise_sets s USING exercise_movements m, exercises e
            WHERE s.id = %s AND s.movement_id = m.id AND m.exercise_id = e.id AND e.user_id = %s
            RETURNING s.id
            """,
            (set_id, user["id"]),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到這組紀錄")
    return {"ok": True}
