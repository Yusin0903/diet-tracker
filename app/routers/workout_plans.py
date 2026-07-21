"""訓練菜單:可重複套用的重訓範本(動作 + 目標組數/次數 + 可選出處連結)。

雙向都支援:
- 套用菜單到今天(見 app.routers.exercises 的 /from-plan/{id})會把動作/組數/次數
  複製成當天的實際運動記錄,使用者只要調整每組的重量即可,不必每次重打一次。
- 把今天已經記錄好的重訓存成新菜單(這裡的 /from-exercise/{id}),下次就能直接套用,
  不用每次都手動重建同一份菜單。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Exercise, ExerciseMovement, ExerciseSet, WorkoutPlan, WorkoutPlanMovement
from app.schemas import PlanIn, PlanMovementIn
from app.security import current_user

router = APIRouter(prefix="/api/workout-plans", tags=["workout-plans"])


def _serialize_movement(m: WorkoutPlanMovement) -> dict:
    return {
        "id": m.id, "name": m.name,
        "target_sets": m.target_sets, "target_reps": m.target_reps,
    }


def _fetch_movements(plan_id: int, db: Session) -> list:
    rows = db.execute(
        select(WorkoutPlanMovement)
        .where(WorkoutPlanMovement.plan_id == plan_id)
        .order_by(WorkoutPlanMovement.sort_order, WorkoutPlanMovement.id)
    ).scalars()
    return [_serialize_movement(m) for m in rows]


def _require_owned_plan(plan_id: int, user_id: int, db: Session) -> WorkoutPlan:
    plan = db.execute(
        select(WorkoutPlan).where(WorkoutPlan.id == plan_id, WorkoutPlan.user_id == user_id)
    ).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="找不到這個菜單")
    return plan


@router.get("")
def list_plans(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(WorkoutPlan, func.count(WorkoutPlanMovement.id))
        .outerjoin(WorkoutPlanMovement, WorkoutPlanMovement.plan_id == WorkoutPlan.id)
        .where(WorkoutPlan.user_id == user["id"])
        .group_by(WorkoutPlan.id)
        .order_by(WorkoutPlan.updated_at.desc())
    ).all()
    return [
        {
            "id": p.id, "name": p.name, "source_url": p.source_url or "",
            "movement_count": count,
        }
        for p, count in rows
    ]


@router.post("")
def create_plan(
    body: PlanIn, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    plan = WorkoutPlan(user_id=user["id"], name=body.name, source_url=body.source_url)
    db.add(plan)
    db.flush()
    return {"id": plan.id, "name": plan.name, "source_url": plan.source_url or "", "movements": []}


@router.get("/{plan_id}")
def get_plan(
    plan_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    plan = _require_owned_plan(plan_id, user["id"], db)
    return {
        "id": plan.id, "name": plan.name, "source_url": plan.source_url or "",
        "movements": _fetch_movements(plan_id, db),
    }


@router.put("/{plan_id}")
def update_plan(
    plan_id: int, body: PlanIn, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    plan = _require_owned_plan(plan_id, user["id"], db)
    plan.name = body.name
    plan.source_url = body.source_url
    db.flush()
    return {
        "id": plan.id, "name": plan.name, "source_url": plan.source_url or "",
        "movements": _fetch_movements(plan_id, db),
    }


@router.delete("/{plan_id}")
def delete_plan(
    plan_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    plan = _require_owned_plan(plan_id, user["id"], db)
    db.delete(plan)
    return {"ok": True}


@router.post("/{plan_id}/movements")
def add_movement(
    plan_id: int,
    body: PlanMovementIn,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_owned_plan(plan_id, user["id"], db)
    next_order = db.execute(
        select(func.coalesce(func.max(WorkoutPlanMovement.sort_order), -1) + 1).where(
            WorkoutPlanMovement.plan_id == plan_id
        )
    ).scalar_one()
    movement = WorkoutPlanMovement(
        plan_id=plan_id,
        name=body.name,
        target_sets=body.target_sets,
        target_reps=body.target_reps,
        sort_order=next_order,
    )
    db.add(movement)
    db.flush()
    return _serialize_movement(movement)


@router.put("/movements/{movement_id}")
def edit_movement(
    movement_id: int,
    body: PlanMovementIn,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    movement = db.execute(
        select(WorkoutPlanMovement)
        .join(WorkoutPlan, WorkoutPlan.id == WorkoutPlanMovement.plan_id)
        .where(WorkoutPlanMovement.id == movement_id, WorkoutPlan.user_id == user["id"])
    ).scalar_one_or_none()
    if movement is None:
        raise HTTPException(status_code=404, detail="找不到這個動作")
    movement.name = body.name
    movement.target_sets = body.target_sets
    movement.target_reps = body.target_reps
    db.flush()
    return _serialize_movement(movement)


@router.delete("/movements/{movement_id}")
def delete_movement(
    movement_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    movement = db.execute(
        select(WorkoutPlanMovement)
        .join(WorkoutPlan, WorkoutPlan.id == WorkoutPlanMovement.plan_id)
        .where(WorkoutPlanMovement.id == movement_id, WorkoutPlan.user_id == user["id"])
    ).scalar_one_or_none()
    if movement is None:
        raise HTTPException(status_code=404, detail="找不到這個動作")
    db.delete(movement)
    return {"ok": True}


@router.post("/from-exercise/{exercise_id}")
def create_from_exercise(
    exercise_id: int,
    body: PlanIn,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    """把一筆已經記錄的重訓(動作 + 組數)存成新菜單,下次直接套用不用重打一次。

    每個動作的目標組數 = 該動作實際記了幾組;目標次數 = 第一組的次數
    (菜單本來就只是抓大概的範本,精確數字每次套用時本來就會重新調整)。
    """
    owned = db.execute(
        select(Exercise.id).where(
            Exercise.id == exercise_id, Exercise.user_id == user["id"], Exercise.ex_type == "strength"
        )
    ).first()
    if owned is None:
        raise HTTPException(status_code=404, detail="找不到這筆重訓記錄")

    movements = db.execute(
        select(ExerciseMovement)
        .where(ExerciseMovement.exercise_id == exercise_id)
        .order_by(ExerciseMovement.sort_order, ExerciseMovement.id)
    ).scalars()
    movement_sets = []
    for m in movements:
        sets = db.execute(
            select(ExerciseSet.reps)
            .where(ExerciseSet.movement_id == m.id)
            .order_by(ExerciseSet.set_order, ExerciseSet.id)
        ).scalars().all()
        movement_sets.append((m.name, sets))

    plan = WorkoutPlan(user_id=user["id"], name=body.name, source_url=body.source_url)
    db.add(plan)
    db.flush()
    for sort_order, (name, reps_list) in enumerate(movement_sets):
        target_sets = len(reps_list) or 1
        target_reps = reps_list[0] if reps_list else 10
        db.add(
            WorkoutPlanMovement(
                plan_id=plan.id, name=name, target_sets=target_sets,
                target_reps=target_reps, sort_order=sort_order,
            )
        )
    db.flush()
    return {
        "id": plan.id, "name": plan.name, "source_url": plan.source_url or "",
        "movements": _fetch_movements(plan.id, db),
    }
