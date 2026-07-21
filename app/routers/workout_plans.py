"""訓練菜單:可重複套用的重訓範本(動作 + 目標組數/次數 + 可選出處連結)。

雙向都支援:
- 套用菜單到今天(見 app.routers.exercises 的 /from-plan/{id})會把動作/組數/次數
  複製成當天的實際運動記錄,使用者只要調整每組的重量即可,不必每次重打一次。
- 把今天已經記錄好的重訓存成新菜單(這裡的 /from-exercise/{id}),下次就能直接套用,
  不用每次都手動重建同一份菜單。
"""
from fastapi import APIRouter, Depends, HTTPException

from app.db import get_cursor
from app.schemas import PlanIn, PlanMovementIn
from app.security import current_user

router = APIRouter(prefix="/api/workout-plans", tags=["workout-plans"])


def _serialize_movement(m: dict) -> dict:
    return {
        "id": m["id"], "name": m["name"],
        "target_sets": m["target_sets"], "target_reps": m["target_reps"],
    }


def _fetch_movements(plan_id: int) -> list:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, name, target_sets, target_reps FROM workout_plan_movements
            WHERE plan_id = %s ORDER BY sort_order, id
            """,
            (plan_id,),
        )
        return [_serialize_movement(m) for m in cur.fetchall()]


def _require_owned_plan(plan_id: int, user_id: int) -> None:
    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM workout_plans WHERE id = %s AND user_id = %s", (plan_id, user_id))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到這個菜單")


@router.get("")
def list_plans(user: dict = Depends(current_user)):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT p.id, p.name, p.source_url, COUNT(m.id) AS movement_count
            FROM workout_plans p LEFT JOIN workout_plan_movements m ON m.plan_id = p.id
            WHERE p.user_id = %s
            GROUP BY p.id ORDER BY p.updated_at DESC
            """,
            (user["id"],),
        )
        rows = cur.fetchall()
    return [
        {
            "id": r["id"], "name": r["name"], "source_url": r["source_url"] or "",
            "movement_count": r["movement_count"],
        }
        for r in rows
    ]


@router.post("")
def create_plan(body: PlanIn, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO workout_plans (user_id, name, source_url) VALUES (%s, %s, %s) RETURNING id, name, source_url",
            (user["id"], body.name, body.source_url),
        )
        row = cur.fetchone()
    return {"id": row["id"], "name": row["name"], "source_url": row["source_url"] or "", "movements": []}


@router.get("/{plan_id}")
def get_plan(plan_id: int, user: dict = Depends(current_user)):
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, source_url FROM workout_plans WHERE id = %s AND user_id = %s",
            (plan_id, user["id"]),
        )
        plan = cur.fetchone()
    if plan is None:
        raise HTTPException(status_code=404, detail="找不到這個菜單")
    return {
        "id": plan["id"], "name": plan["name"], "source_url": plan["source_url"] or "",
        "movements": _fetch_movements(plan_id),
    }


@router.put("/{plan_id}")
def update_plan(plan_id: int, body: PlanIn, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE workout_plans SET name = %s, source_url = %s, updated_at = now()
            WHERE id = %s AND user_id = %s RETURNING id, name, source_url
            """,
            (body.name, body.source_url, plan_id, user["id"]),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="找不到這個菜單")
    return {
        "id": row["id"], "name": row["name"], "source_url": row["source_url"] or "",
        "movements": _fetch_movements(plan_id),
    }


@router.delete("/{plan_id}")
def delete_plan(plan_id: int, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM workout_plans WHERE id = %s AND user_id = %s RETURNING id", (plan_id, user["id"])
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到這個菜單")
    return {"ok": True}


@router.post("/{plan_id}/movements")
def add_movement(plan_id: int, body: PlanMovementIn, user: dict = Depends(current_user)):
    _require_owned_plan(plan_id, user["id"])
    with get_cursor(commit=True) as cur:
        cur.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next FROM workout_plan_movements WHERE plan_id = %s",
            (plan_id,),
        )
        next_order = cur.fetchone()["next"]
        cur.execute(
            """
            INSERT INTO workout_plan_movements (plan_id, name, target_sets, target_reps, sort_order)
            VALUES (%s, %s, %s, %s, %s) RETURNING id, name, target_sets, target_reps
            """,
            (plan_id, body.name, body.target_sets, body.target_reps, next_order),
        )
        row = cur.fetchone()
    return _serialize_movement(row)


@router.put("/movements/{movement_id}")
def edit_movement(movement_id: int, body: PlanMovementIn, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE workout_plan_movements m SET name = %s, target_sets = %s, target_reps = %s
            FROM workout_plans p
            WHERE m.id = %s AND m.plan_id = p.id AND p.user_id = %s
            RETURNING m.id, m.name, m.target_sets, m.target_reps
            """,
            (body.name, body.target_sets, body.target_reps, movement_id, user["id"]),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="找不到這個動作")
    return _serialize_movement(row)


@router.delete("/movements/{movement_id}")
def delete_movement(movement_id: int, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            DELETE FROM workout_plan_movements m USING workout_plans p
            WHERE m.id = %s AND m.plan_id = p.id AND p.user_id = %s
            RETURNING m.id
            """,
            (movement_id, user["id"]),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到這個動作")
    return {"ok": True}


@router.post("/from-exercise/{exercise_id}")
def create_from_exercise(exercise_id: int, body: PlanIn, user: dict = Depends(current_user)):
    """把一筆已經記錄的重訓(動作 + 組數)存成新菜單,下次直接套用不用重打一次。

    每個動作的目標組數 = 該動作實際記了幾組;目標次數 = 第一組的次數
    (菜單本來就只是抓大概的範本,精確數字每次套用時本來就會重新調整)。
    """
    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM exercises WHERE id = %s AND user_id = %s AND ex_type = 'strength'",
            (exercise_id, user["id"]),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到這筆重訓記錄")
        cur.execute(
            "SELECT id, name FROM exercise_movements WHERE exercise_id = %s ORDER BY sort_order, id",
            (exercise_id,),
        )
        movements = cur.fetchall()
        movement_sets = []
        for m in movements:
            cur.execute(
                "SELECT reps FROM exercise_sets WHERE movement_id = %s ORDER BY set_order, id",
                (m["id"],),
            )
            movement_sets.append((m["name"], cur.fetchall()))

    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO workout_plans (user_id, name, source_url) VALUES (%s, %s, %s) RETURNING id, name, source_url",
            (user["id"], body.name, body.source_url),
        )
        plan = cur.fetchone()
        for sort_order, (name, sets) in enumerate(movement_sets):
            target_sets = len(sets) or 1
            target_reps = sets[0]["reps"] if sets else 10
            cur.execute(
                """
                INSERT INTO workout_plan_movements (plan_id, name, target_sets, target_reps, sort_order)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (plan["id"], name, target_sets, target_reps, sort_order),
            )
    return {
        "id": plan["id"], "name": plan["name"], "source_url": plan["source_url"] or "",
        "movements": _fetch_movements(plan["id"]),
    }
