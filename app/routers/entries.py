"""飲食記錄:新增 / 查當日 / 刪除。資料皆以登入會員為界,依其時區算當日。"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_cursor
from app.deps import day_bounds, resolve_tz, serialize_entry
from app.schemas import EntryEdit, EntryIn
from app.security import current_user

router = APIRouter(prefix="/api/entries", tags=["entries"])


@router.post("")
def create_entry(
    body: EntryIn,
    date: Optional[str] = None,
    tz: Optional[str] = None,
    user: dict = Depends(current_user),
):
    if body.source not in ("photo", "manual", "favorite", "barcode", "recipe"):
        raise HTTPException(status_code=400, detail="source 不合法")
    zone = resolve_tz(tz)
    if date:
        # 補記過去的日子:錨定到那一天,但保留現在的時刻,同一天多筆補記時順序才合理。
        start, _, _ = day_bounds(date, zone)
        if start.date() > datetime.now(zone).date():
            raise HTTPException(status_code=400, detail="不能記錄未來的日期")
        eaten_at = datetime.combine(start.date(), datetime.now(zone).time(), tzinfo=zone)
    else:
        eaten_at = datetime.now(zone)
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO entries (user_id, eaten_at, name, calories, protein_g, source, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, eaten_at, name, calories, protein_g, source, note
            """,
            (user["id"], eaten_at, body.name, body.calories, body.protein_g, body.source, body.note),
        )
        row = cur.fetchone()
    return serialize_entry(row, zone)


@router.get("")
def list_entries(
    date: Optional[str] = None,
    tz: Optional[str] = None,
    user: dict = Depends(current_user),
):
    zone = resolve_tz(tz)
    start, end, _ = day_bounds(date, zone)
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, eaten_at, name, calories, protein_g, source, note
            FROM entries
            WHERE user_id = %s AND eaten_at >= %s AND eaten_at < %s
            ORDER BY eaten_at DESC
            """,
            (user["id"], start, end),
        )
        rows = cur.fetchall()
    return [serialize_entry(r, zone) for r in rows]


@router.put("/{entry_id}")
def update_entry(
    entry_id: int,
    body: EntryEdit,
    tz: Optional[str] = None,
    user: dict = Depends(current_user),
):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE entries SET name = %s, calories = %s, protein_g = %s, note = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, eaten_at, name, calories, protein_g, source, note
            """,
            (body.name, body.calories, body.protein_g, body.note, entry_id, user["id"]),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="找不到這筆記錄")
    return serialize_entry(row, resolve_tz(tz))


@router.delete("/{entry_id}")
def delete_entry(entry_id: int, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM entries WHERE id = %s AND user_id = %s RETURNING id",
            (entry_id, user["id"]),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到這筆記錄")
    return {"ok": True}
