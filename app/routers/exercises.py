"""運動記錄:新增 / 查當日 / 查整月打卡狀態 / 刪除,重訓的動作與組數細節,以及套用訓練菜單。

先求養成紀錄習慣:時長與熱量都不強制、不自動估算,只在乎「今天有沒有動」。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_cursor
from app.deps import day_bounds, resolve_tz
from app.schemas import ExerciseIn, MovementIn, SetIn
from app.security import current_user
from app.services.exercise import compute_streak, month_marks

router = APIRouter(prefix="/api/exercises", tags=["exercises"])


def _serialize(r: dict, tz) -> dict:
    return {
        "id": r["id"],
        "logged_at": r["logged_at"].astimezone(tz).isoformat(),
        "ex_type": r["ex_type"],
        "distance_km": float(r["distance_km"]) if r["distance_km"] is not None else None,
        "note": r["note"],
    }


@router.post("")
def create_exercise(
    body: ExerciseIn, tz: Optional[str] = None, user: dict = Depends(current_user)
):
    zone = resolve_tz(tz)
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO exercises (user_id, ex_type, distance_km, note)
            VALUES (%s, %s, %s, %s)
            RETURNING id, logged_at, ex_type, distance_km, note
            """,
            (user["id"], body.ex_type, body.distance_km, body.note),
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
            SELECT id, logged_at, ex_type, distance_km, note
            FROM exercises
            WHERE user_id = %s AND logged_at >= %s AND logged_at < %s
            ORDER BY logged_at DESC
            """,
            (user["id"], start, end),
        )
        rows = cur.fetchall()
    return {"date": day_str, "items": [_serialize(r, zone) for r in rows]}


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


# ---------- 重訓明細:動作 + 組數(純訓練內容,不影響/不需要熱量) ----------
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


def _fetch_movements(exercise_id: int) -> list:
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


@router.get("/{exercise_id}/movements")
def list_movements(exercise_id: int, user: dict = Depends(current_user)):
    _require_owned_exercise(exercise_id, user["id"])
    return _fetch_movements(exercise_id)


@router.post("/from-plan/{plan_id}")
def create_from_plan(
    plan_id: int, tz: Optional[str] = None, user: dict = Depends(current_user)
):
    """依照一份訓練菜單開始今天的紀錄:動作/組數/次數直接複製過來,重量留空給使用者調整。"""
    zone = resolve_tz(tz)
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name FROM workout_plans WHERE id = %s AND user_id = %s", (plan_id, user["id"])
        )
        plan = cur.fetchone()
    if plan is None:
        raise HTTPException(status_code=404, detail="找不到這個菜單")
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO exercises (user_id, ex_type, note)
            VALUES (%s, 'strength', %s)
            RETURNING id, logged_at, ex_type, distance_km, note
            """,
            (user["id"], f"依照《{plan['name']}》菜單"),
        )
        ex_row = cur.fetchone()
        eid = ex_row["id"]
        cur.execute(
            """
            SELECT name, target_sets, target_reps, sort_order FROM workout_plan_movements
            WHERE plan_id = %s ORDER BY sort_order, id
            """,
            (plan_id,),
        )
        for pm in cur.fetchall():
            cur.execute(
                "INSERT INTO exercise_movements (exercise_id, name, sort_order) VALUES (%s, %s, %s) RETURNING id",
                (eid, pm["name"], pm["sort_order"]),
            )
            mid = cur.fetchone()["id"]
            for i in range(pm["target_sets"]):
                cur.execute(
                    "INSERT INTO exercise_sets (movement_id, set_order, weight_kg, reps) VALUES (%s, %s, NULL, %s)",
                    (mid, i, pm["target_reps"]),
                )
    return {"exercise": _serialize(ex_row, zone), "movements": _fetch_movements(eid)}


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
