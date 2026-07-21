"""好友系統 + 分享權限。

- 邀請 / 接受 / 移除好友。
- 每位使用者一組分享權限(熊狀態 / 飲食記錄 / 食譜),套用到所有好友。
- 看好友資料時,嚴格依「對方的」分享權限過濾。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

from app.db import get_db
from app.deps import day_bounds, resolve_tz, serialize_entry
from app.models import Entry, Friendship, Recipe, SharePrefs, User
from app.schemas import FriendRequestIn, SharePrefsIn
from app.security import current_user
from app.services.summary import day_summary, mascot_only

router = APIRouter(prefix="/api", tags=["friends"])

DEFAULT_PREFS = {"share_mascot": True, "share_diet": False, "share_recipes": False}


def _prefs(user_id: int, db: Session) -> dict:
    p = db.get(SharePrefs, user_id)
    if not p:
        return dict(DEFAULT_PREFS)
    return {"share_mascot": p.share_mascot, "share_diet": p.share_diet, "share_recipes": p.share_recipes}


def _are_friends(a: int, b: int, db: Session) -> bool:
    found = db.execute(
        select(Friendship.id).where(
            Friendship.status == "accepted",
            or_(
                and_(Friendship.requester_id == a, Friendship.addressee_id == b),
                and_(Friendship.requester_id == b, Friendship.addressee_id == a),
            ),
        )
    ).first()
    return found is not None


# ---------- 分享權限 ----------
@router.get("/share")
def get_share(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    return _prefs(user["id"], db)


@router.put("/share")
def set_share(
    body: SharePrefsIn, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    stmt = (
        pg_insert(SharePrefs)
        .values(
            user_id=user["id"],
            share_mascot=body.share_mascot,
            share_diet=body.share_diet,
            share_recipes=body.share_recipes,
        )
        .on_conflict_do_update(
            index_elements=[SharePrefs.user_id],
            set_={
                "share_mascot": body.share_mascot,
                "share_diet": body.share_diet,
                "share_recipes": body.share_recipes,
            },
        )
    )
    db.execute(stmt)
    return _prefs(user["id"], db)


# ---------- 好友清單 / 邀請 ----------
@router.get("/friends")
def list_friends(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    me = user["id"]
    ReqUser = aliased(User)
    AddUser = aliased(User)

    rows = db.execute(
        select(Friendship, ReqUser.username, AddUser.username)
        .join(ReqUser, ReqUser.id == Friendship.requester_id)
        .join(AddUser, AddUser.id == Friendship.addressee_id)
        .where(
            Friendship.status == "accepted",
            or_(Friendship.requester_id == me, Friendship.addressee_id == me),
        )
        .order_by(Friendship.created_at.desc())
    ).all()
    friends = []
    for f, req_name, add_name in rows:
        other_id = f.addressee_id if f.requester_id == me else f.requester_id
        other_name = add_name if f.requester_id == me else req_name
        friends.append({
            "friendship_id": f.id,
            "user_id": other_id,
            "username": other_name,
            "shares": _prefs(other_id, db),  # 對方分享了什麼,前端據此顯示
        })

    # 別人寄給我的邀請(待我接受)
    incoming_rows = db.execute(
        select(Friendship.id, User.username)
        .join(User, User.id == Friendship.requester_id)
        .where(Friendship.addressee_id == me, Friendship.status == "pending")
        .order_by(Friendship.created_at.desc())
    ).all()
    incoming = [{"friendship_id": fid, "username": name} for fid, name in incoming_rows]

    # 我寄出、等待對方的邀請
    outgoing_rows = db.execute(
        select(Friendship.id, User.username)
        .join(User, User.id == Friendship.addressee_id)
        .where(Friendship.requester_id == me, Friendship.status == "pending")
        .order_by(Friendship.created_at.desc())
    ).all()
    outgoing = [{"friendship_id": fid, "username": name} for fid, name in outgoing_rows]

    return {"friends": friends, "incoming": incoming, "outgoing": outgoing}


@router.post("/friends/request")
def request_friend(
    body: FriendRequestIn, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    me = user["id"]
    target = body.username.strip()
    other_id = db.execute(select(User.id).where(User.username == target)).scalar_one_or_none()
    if not other_id:
        raise HTTPException(status_code=404, detail="找不到這個帳號")
    if other_id == me:
        raise HTTPException(status_code=400, detail="不能加自己")

    # 對方已寄邀請給我 → 直接成為好友
    rev = db.execute(
        select(Friendship).where(Friendship.requester_id == other_id, Friendship.addressee_id == me)
    ).scalar_one_or_none()
    if rev:
        if rev.status != "accepted":
            rev.status = "accepted"
        return {"status": "accepted"}

    # 我已寄過 / 已是好友
    mine_status = db.execute(
        select(Friendship.status).where(Friendship.requester_id == me, Friendship.addressee_id == other_id)
    ).scalar_one_or_none()
    if mine_status:
        return {"status": mine_status}

    db.add(Friendship(requester_id=me, addressee_id=other_id, status="pending"))
    return {"status": "pending"}


@router.post("/friends/{friendship_id}/accept")
def accept_friend(
    friendship_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    friendship = db.execute(
        select(Friendship).where(
            Friendship.id == friendship_id, Friendship.addressee_id == user["id"], Friendship.status == "pending"
        )
    ).scalar_one_or_none()
    if friendship is None:
        raise HTTPException(status_code=404, detail="找不到這個邀請")
    friendship.status = "accepted"
    return {"ok": True}


@router.delete("/friends/{friendship_id}")
def remove_friend(
    friendship_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    """拒絕邀請或移除好友(任一方皆可)。"""
    me = user["id"]
    friendship = db.execute(
        select(Friendship).where(
            Friendship.id == friendship_id,
            or_(Friendship.requester_id == me, Friendship.addressee_id == me),
        )
    ).scalar_one_or_none()
    if friendship is None:
        raise HTTPException(status_code=404, detail="找不到")
    db.delete(friendship)
    return {"ok": True}


# ---------- 看好友資料(依對方權限過濾) ----------
@router.get("/friends/{friend_uid}/feed")
def friend_feed(
    friend_uid: int,
    date: Optional[str] = None,
    tz: Optional[str] = None,
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not _are_friends(user["id"], friend_uid, db):
        raise HTTPException(status_code=403, detail="你們還不是好友")

    username = db.execute(select(User.username).where(User.id == friend_uid)).scalar_one_or_none()
    if not username:
        raise HTTPException(status_code=404, detail="找不到使用者")

    p = _prefs(friend_uid, db)
    zone = resolve_tz(tz)
    start, end, day_str = day_bounds(date, zone)
    out = {"username": username, "date": day_str, "shares": p}

    if p["share_diet"]:
        ds = day_summary(friend_uid, start, end, db)
        out["summary"] = ds
        rows = db.execute(
            select(Entry)
            .where(Entry.user_id == friend_uid, Entry.eaten_at >= start, Entry.eaten_at < end)
            .order_by(Entry.eaten_at.desc())
        ).scalars()
        out["entries"] = [serialize_entry(r, zone) for r in rows]
    elif p["share_mascot"]:
        out["mascot"] = mascot_only(day_summary(friend_uid, start, end, db))

    if p["share_recipes"]:
        rows = db.execute(
            select(Recipe).where(Recipe.user_id == friend_uid).order_by(Recipe.updated_at.desc())
        ).scalars()
        out["recipes"] = [
            {
                "id": r.id, "name": r.name,
                "servings": float(r.servings) if r.servings is not None else None,
                "calories": r.calories,
                "protein_g": float(r.protein_g) if r.protein_g is not None else None,
                "ingredients": r.ingredients or "", "steps": r.steps or "",
                "video_url": r.video_url or "",
            }
            for r in rows
        ]
    return out
