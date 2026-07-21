"""常用食物清單(每位會員各自一份)。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Food
from app.schemas import FoodIn
from app.security import current_user

router = APIRouter(prefix="/api/foods", tags=["foods"])


def _row(f: Food) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "calories": f.calories,
        "protein_g": float(f.protein_g),
    }


@router.get("")
def list_foods(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Food).where(Food.user_id == user["id"]).order_by(Food.name)
    ).scalars()
    return [_row(r) for r in rows]


@router.post("")
def create_food(
    body: FoodIn, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    stmt = (
        pg_insert(Food)
        .values(
            user_id=user["id"], name=body.name, calories=body.calories, protein_g=body.protein_g
        )
        .on_conflict_do_update(
            index_elements=[Food.user_id, Food.name],
            set_={"calories": body.calories, "protein_g": body.protein_g},
        )
        .returning(Food)
    )
    food = db.scalars(stmt).one()
    return _row(food)


@router.delete("/{food_id}")
def delete_food(
    food_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    food = db.execute(
        select(Food).where(Food.id == food_id, Food.user_id == user["id"])
    ).scalar_one_or_none()
    if food is None:
        raise HTTPException(status_code=404, detail="找不到這個食物")
    db.delete(food)
    return {"ok": True}
