"""常用食物清單(每位會員各自一份)。"""
from fastapi import APIRouter, Depends, HTTPException

from app.db import get_cursor
from app.schemas import FoodIn
from app.security import current_user

router = APIRouter(prefix="/api/foods", tags=["foods"])


def _row(r: dict) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "calories": r["calories"],
        "protein_g": float(r["protein_g"]),
    }


@router.get("")
def list_foods(user: dict = Depends(current_user)):
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, calories, protein_g FROM foods WHERE user_id = %s ORDER BY name",
            (user["id"],),
        )
        return [_row(r) for r in cur.fetchall()]


@router.post("")
def create_food(body: FoodIn, user: dict = Depends(current_user)):
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
        return _row(cur.fetchone())


@router.delete("/{food_id}")
def delete_food(food_id: int, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM foods WHERE id = %s AND user_id = %s RETURNING id",
            (food_id, user["id"]),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到這個食物")
    return {"ok": True}
