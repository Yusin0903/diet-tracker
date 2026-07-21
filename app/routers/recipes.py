"""食譜:每位會員自己記的食譜(名稱 / 份數 / 每份熱量蛋白 / 食材 / 步驟)。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Recipe
from app.schemas import RecipeIn
from app.security import current_user

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


def _row(r: Recipe) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "servings": float(r.servings) if r.servings is not None else None,
        "calories": r.calories,
        "protein_g": float(r.protein_g) if r.protein_g is not None else None,
        "ingredients": r.ingredients or "",
        "steps": r.steps or "",
        "video_url": r.video_url or "",
    }


@router.get("")
def list_recipes(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Recipe).where(Recipe.user_id == user["id"]).order_by(Recipe.updated_at.desc())
    ).scalars()
    return [_row(r) for r in rows]


@router.post("")
def create_recipe(
    body: RecipeIn, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    recipe = Recipe(
        user_id=user["id"],
        name=body.name,
        servings=body.servings,
        calories=body.calories,
        protein_g=body.protein_g,
        ingredients=body.ingredients,
        steps=body.steps,
        video_url=body.video_url,
    )
    db.add(recipe)
    db.flush()
    return _row(recipe)


@router.put("/{recipe_id}")
def update_recipe(
    recipe_id: int,
    body: RecipeIn,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    recipe = db.execute(
        select(Recipe).where(Recipe.id == recipe_id, Recipe.user_id == user["id"])
    ).scalar_one_or_none()
    if recipe is None:
        raise HTTPException(status_code=404, detail="找不到這個食譜")
    recipe.name = body.name
    recipe.servings = body.servings
    recipe.calories = body.calories
    recipe.protein_g = body.protein_g
    recipe.ingredients = body.ingredients
    recipe.steps = body.steps
    recipe.video_url = body.video_url
    db.flush()
    return _row(recipe)


@router.delete("/{recipe_id}")
def delete_recipe(
    recipe_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    recipe = db.execute(
        select(Recipe).where(Recipe.id == recipe_id, Recipe.user_id == user["id"])
    ).scalar_one_or_none()
    if recipe is None:
        raise HTTPException(status_code=404, detail="找不到這個食譜")
    db.delete(recipe)
    return {"ok": True}
