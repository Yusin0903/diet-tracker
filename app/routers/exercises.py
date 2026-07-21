"""運動記錄:新增 / 查當日 / 查整月打卡狀態 / 刪除,重訓的動作與組數細節,以及套用訓練菜單。

先求養成紀錄習慣:時長與熱量都不強制、不自動估算,只在乎「今天有沒有動」。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import day_bounds, resolve_tz
from app.models import Exercise, ExerciseMovement, ExerciseSet, WorkoutPlan, WorkoutPlanMovement
from app.schemas import ExerciseIn, MovementIn, SetIn
from app.security import current_user
from app.services.exercise import compute_streak, month_marks

router = APIRouter(prefix="/api/exercises", tags=["exercises"])


def _serialize(e: Exercise, tz) -> dict:
    return {
        "id": e.id,
        "logged_at": e.logged_at.astimezone(tz).isoformat(),
        "ex_type": e.ex_type,
        "distance_km": float(e.distance_km) if e.distance_km is not None else None,
        "note": e.note,
    }


@router.post("")
def create_exercise(
    body: ExerciseIn,
    tz: Optional[str] = None,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    zone = resolve_tz(tz)
    exercise = Exercise(
        user_id=user["id"], ex_type=body.ex_type, distance_km=body.distance_km, note=body.note
    )
    db.add(exercise)
    db.flush()
    return _serialize(exercise, zone)


@router.get("")
def list_exercises(
    date: Optional[str] = None,
    tz: Optional[str] = None,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    zone = resolve_tz(tz)
    start, end, day_str = day_bounds(date, zone)
    rows = db.execute(
        select(Exercise)
        .where(Exercise.user_id == user["id"], Exercise.logged_at >= start, Exercise.logged_at < end)
        .order_by(Exercise.logged_at.desc())
    ).scalars()
    return {"date": day_str, "items": [_serialize(r, zone) for r in rows]}


@router.get("/month")
def month_calendar(
    year: int,
    month: int,
    tz: Optional[str] = None,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="month 需為 1–12")
    zone = resolve_tz(tz)
    return {
        "days": month_marks(user["id"], year, month, zone, db),
        "streak": compute_streak(user["id"], zone, db),
    }


@router.delete("/{exercise_id}")
def delete_exercise(
    exercise_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    exercise = db.execute(
        select(Exercise).where(Exercise.id == exercise_id, Exercise.user_id == user["id"])
    ).scalar_one_or_none()
    if exercise is None:
        raise HTTPException(status_code=404, detail="找不到這筆記錄")
    db.delete(exercise)
    return {"ok": True}


# ---------- 重訓明細:動作 + 組數(純訓練內容,不影響/不需要熱量) ----------
def _serialize_set(s: ExerciseSet) -> dict:
    return {
        "id": s.id,
        "weight_kg": float(s.weight_kg) if s.weight_kg is not None else None,
        "reps": s.reps,
    }


def _require_owned_exercise(exercise_id: int, user_id: int, db: Session) -> None:
    found = db.execute(
        select(Exercise.id).where(Exercise.id == exercise_id, Exercise.user_id == user_id)
    ).first()
    if found is None:
        raise HTTPException(status_code=404, detail="找不到這筆運動記錄")


def _fetch_movements(exercise_id: int, db: Session) -> list:
    movements = db.execute(
        select(ExerciseMovement)
        .where(ExerciseMovement.exercise_id == exercise_id)
        .order_by(ExerciseMovement.sort_order, ExerciseMovement.id)
    ).scalars()
    result = []
    for m in movements:
        sets = db.execute(
            select(ExerciseSet)
            .where(ExerciseSet.movement_id == m.id)
            .order_by(ExerciseSet.set_order, ExerciseSet.id)
        ).scalars()
        result.append({"id": m.id, "name": m.name, "sets": [_serialize_set(s) for s in sets]})
    return result


@router.get("/{exercise_id}/movements")
def list_movements(
    exercise_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    _require_owned_exercise(exercise_id, user["id"], db)
    return _fetch_movements(exercise_id, db)


@router.post("/from-plan/{plan_id}")
def create_from_plan(
    plan_id: int,
    tz: Optional[str] = None,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    """依照一份訓練菜單開始今天的紀錄:動作/組數/次數直接複製過來,重量留空給使用者調整。"""
    zone = resolve_tz(tz)
    plan = db.execute(
        select(WorkoutPlan).where(WorkoutPlan.id == plan_id, WorkoutPlan.user_id == user["id"])
    ).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="找不到這個菜單")

    exercise = Exercise(user_id=user["id"], ex_type="strength", note=f"依照《{plan.name}》菜單")
    db.add(exercise)
    db.flush()

    plan_movements = db.execute(
        select(WorkoutPlanMovement)
        .where(WorkoutPlanMovement.plan_id == plan_id)
        .order_by(WorkoutPlanMovement.sort_order, WorkoutPlanMovement.id)
    ).scalars()
    for pm in plan_movements:
        movement = ExerciseMovement(exercise_id=exercise.id, name=pm.name, sort_order=pm.sort_order)
        db.add(movement)
        db.flush()
        for i in range(pm.target_sets):
            db.add(
                ExerciseSet(movement_id=movement.id, set_order=i, weight_kg=None, reps=pm.target_reps)
            )

    db.flush()
    return {"exercise": _serialize(exercise, zone), "movements": _fetch_movements(exercise.id, db)}


@router.post("/{exercise_id}/movements")
def add_movement(
    exercise_id: int,
    body: MovementIn,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_owned_exercise(exercise_id, user["id"], db)
    next_order = db.execute(
        select(func.coalesce(func.max(ExerciseMovement.sort_order), -1) + 1).where(
            ExerciseMovement.exercise_id == exercise_id
        )
    ).scalar_one()
    movement = ExerciseMovement(exercise_id=exercise_id, name=body.name, sort_order=next_order)
    db.add(movement)
    db.flush()
    return {"id": movement.id, "name": movement.name, "sets": []}


@router.delete("/movements/{movement_id}")
def delete_movement(
    movement_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    movement = db.execute(
        select(ExerciseMovement)
        .join(Exercise, Exercise.id == ExerciseMovement.exercise_id)
        .where(ExerciseMovement.id == movement_id, Exercise.user_id == user["id"])
    ).scalar_one_or_none()
    if movement is None:
        raise HTTPException(status_code=404, detail="找不到這個動作")
    db.delete(movement)
    return {"ok": True}


@router.post("/movements/{movement_id}/sets")
def add_set(
    movement_id: int, body: SetIn, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    owned = db.execute(
        select(ExerciseMovement.id)
        .join(Exercise, Exercise.id == ExerciseMovement.exercise_id)
        .where(ExerciseMovement.id == movement_id, Exercise.user_id == user["id"])
    ).first()
    if owned is None:
        raise HTTPException(status_code=404, detail="找不到這個動作")
    next_order = db.execute(
        select(func.coalesce(func.max(ExerciseSet.set_order), -1) + 1).where(
            ExerciseSet.movement_id == movement_id
        )
    ).scalar_one()
    ex_set = ExerciseSet(
        movement_id=movement_id, set_order=next_order, weight_kg=body.weight_kg, reps=body.reps
    )
    db.add(ex_set)
    db.flush()
    return _serialize_set(ex_set)


@router.put("/sets/{set_id}")
def edit_set(
    set_id: int, body: SetIn, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    ex_set = db.execute(
        select(ExerciseSet)
        .join(ExerciseMovement, ExerciseMovement.id == ExerciseSet.movement_id)
        .join(Exercise, Exercise.id == ExerciseMovement.exercise_id)
        .where(ExerciseSet.id == set_id, Exercise.user_id == user["id"])
    ).scalar_one_or_none()
    if ex_set is None:
        raise HTTPException(status_code=404, detail="找不到這組紀錄")
    ex_set.weight_kg = body.weight_kg
    ex_set.reps = body.reps
    db.flush()
    return _serialize_set(ex_set)


@router.delete("/sets/{set_id}")
def delete_set(
    set_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    ex_set = db.execute(
        select(ExerciseSet)
        .join(ExerciseMovement, ExerciseMovement.id == ExerciseSet.movement_id)
        .join(Exercise, Exercise.id == ExerciseMovement.exercise_id)
        .where(ExerciseSet.id == set_id, Exercise.user_id == user["id"])
    ).scalar_one_or_none()
    if ex_set is None:
        raise HTTPException(status_code=404, detail="找不到這組紀錄")
    db.delete(ex_set)
    return {"ok": True}
