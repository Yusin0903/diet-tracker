"""食譜:每位會員自己記的食譜(名稱 / 份數 / 每份熱量蛋白 / 食材 / 步驟)。"""
from fastapi import APIRouter, Depends, HTTPException

from app.db import get_cursor
from app.schemas import RecipeIn
from app.security import current_user

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


def _row(r: dict) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "servings": float(r["servings"]) if r["servings"] is not None else None,
        "calories": r["calories"],
        "protein_g": float(r["protein_g"]) if r["protein_g"] is not None else None,
        "ingredients": r["ingredients"] or "",
        "steps": r["steps"] or "",
    }


@router.get("")
def list_recipes(user: dict = Depends(current_user)):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, name, servings, calories, protein_g, ingredients, steps
            FROM recipes WHERE user_id = %s ORDER BY updated_at DESC
            """,
            (user["id"],),
        )
        return [_row(r) for r in cur.fetchall()]


@router.post("")
def create_recipe(body: RecipeIn, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO recipes (user_id, name, servings, calories, protein_g, ingredients, steps)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, name, servings, calories, protein_g, ingredients, steps
            """,
            (user["id"], body.name, body.servings, body.calories, body.protein_g,
             body.ingredients, body.steps),
        )
        return _row(cur.fetchone())


@router.put("/{recipe_id}")
def update_recipe(recipe_id: int, body: RecipeIn, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE recipes SET name = %s, servings = %s, calories = %s, protein_g = %s,
                   ingredients = %s, steps = %s, updated_at = now()
            WHERE id = %s AND user_id = %s
            RETURNING id, name, servings, calories, protein_g, ingredients, steps
            """,
            (body.name, body.servings, body.calories, body.protein_g,
             body.ingredients, body.steps, recipe_id, user["id"]),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="找不到這個食譜")
        return _row(row)


@router.delete("/{recipe_id}")
def delete_recipe(recipe_id: int, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM recipes WHERE id = %s AND user_id = %s RETURNING id",
            (recipe_id, user["id"]),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到這個食譜")
    return {"ok": True}
