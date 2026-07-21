"""飲食記錄:新增 / 查當日 / 刪除。資料皆以登入會員為界,依其時區算當日。"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import day_bounds, resolve_tz, serialize_entry
from app.models import Entry
from app.schemas import EntryEdit, EntryIn
from app.security import current_user

router = APIRouter(prefix="/api/entries", tags=["entries"])


@router.post("")
def create_entry(
    body: EntryIn,
    date: Optional[str] = None,
    tz: Optional[str] = None,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
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

    entry = Entry(
        user_id=user["id"],
        eaten_at=eaten_at,
        name=body.name,
        calories=body.calories,
        protein_g=body.protein_g,
        source=body.source,
        note=body.note,
    )
    db.add(entry)
    db.flush()
    return serialize_entry(entry, zone)


@router.get("")
def list_entries(
    date: Optional[str] = None,
    tz: Optional[str] = None,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    zone = resolve_tz(tz)
    start, end, _ = day_bounds(date, zone)
    rows = db.execute(
        select(Entry)
        .where(Entry.user_id == user["id"], Entry.eaten_at >= start, Entry.eaten_at < end)
        .order_by(Entry.eaten_at.desc())
    ).scalars()
    return [serialize_entry(r, zone) for r in rows]


@router.put("/{entry_id}")
def update_entry(
    entry_id: int,
    body: EntryEdit,
    tz: Optional[str] = None,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    entry = db.execute(
        select(Entry).where(Entry.id == entry_id, Entry.user_id == user["id"])
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="找不到這筆記錄")
    entry.name = body.name
    entry.calories = body.calories
    entry.protein_g = body.protein_g
    entry.note = body.note
    db.flush()
    return serialize_entry(entry, resolve_tz(tz))


@router.delete("/{entry_id}")
def delete_entry(
    entry_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    entry = db.execute(
        select(Entry).where(Entry.id == entry_id, Entry.user_id == user["id"])
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="找不到這筆記錄")
    db.delete(entry)
    return {"ok": True}
