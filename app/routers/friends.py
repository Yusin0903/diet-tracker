"""好友系統 + 分享權限。

- 邀請 / 接受 / 移除好友。
- 每位使用者一組分享權限(熊狀態 / 飲食記錄 / 食譜),套用到所有好友。
- 看好友資料時,嚴格依「對方的」分享權限過濾。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_cursor
from app.deps import day_bounds, resolve_tz, serialize_entry
from app.schemas import FriendRequestIn, SharePrefsIn
from app.security import current_user
from app.services.summary import day_summary, mascot_only

router = APIRouter(prefix="/api", tags=["friends"])

DEFAULT_PREFS = {"share_mascot": True, "share_diet": False, "share_recipes": False}


def _prefs(user_id: int) -> dict:
    with get_cursor() as cur:
        cur.execute(
            "SELECT share_mascot, share_diet, share_recipes FROM share_prefs WHERE user_id = %s",
            (user_id,),
        )
        r = cur.fetchone()
    if not r:
        return dict(DEFAULT_PREFS)
    return {"share_mascot": r["share_mascot"], "share_diet": r["share_diet"], "share_recipes": r["share_recipes"]}


def _are_friends(a: int, b: int) -> bool:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM friendships
            WHERE status = 'accepted'
              AND ((requester_id = %s AND addressee_id = %s)
                OR (requester_id = %s AND addressee_id = %s))
            """,
            (a, b, b, a),
        )
        return cur.fetchone() is not None


# ---------- 分享權限 ----------
@router.get("/share")
def get_share(user: dict = Depends(current_user)):
    return _prefs(user["id"])


@router.put("/share")
def set_share(body: SharePrefsIn, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO share_prefs (user_id, share_mascot, share_diet, share_recipes)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                share_mascot = EXCLUDED.share_mascot,
                share_diet = EXCLUDED.share_diet,
                share_recipes = EXCLUDED.share_recipes
            """,
            (user["id"], body.share_mascot, body.share_diet, body.share_recipes),
        )
    return _prefs(user["id"])


# ---------- 好友清單 / 邀請 ----------
@router.get("/friends")
def list_friends(user: dict = Depends(current_user)):
    me = user["id"]
    with get_cursor() as cur:
        # 已成為好友(雙向)
        cur.execute(
            """
            SELECT f.id, f.requester_id, f.addressee_id,
                   u_req.username AS req_name, u_add.username AS add_name
            FROM friendships f
            JOIN users u_req ON u_req.id = f.requester_id
            JOIN users u_add ON u_add.id = f.addressee_id
            WHERE f.status = 'accepted' AND (f.requester_id = %s OR f.addressee_id = %s)
            ORDER BY f.created_at DESC
            """,
            (me, me),
        )
        friends = []
        for r in cur.fetchall():
            other_id = r["addressee_id"] if r["requester_id"] == me else r["requester_id"]
            other_name = r["add_name"] if r["requester_id"] == me else r["req_name"]
            p = _prefs(other_id)
            friends.append({
                "friendship_id": r["id"],
                "user_id": other_id,
                "username": other_name,
                "shares": p,  # 對方分享了什麼,前端據此顯示
            })

        # 別人寄給我的邀請(待我接受)
        cur.execute(
            """
            SELECT f.id, u.username FROM friendships f
            JOIN users u ON u.id = f.requester_id
            WHERE f.addressee_id = %s AND f.status = 'pending'
            ORDER BY f.created_at DESC
            """,
            (me,),
        )
        incoming = [{"friendship_id": r["id"], "username": r["username"]} for r in cur.fetchall()]

        # 我寄出、等待對方的邀請
        cur.execute(
            """
            SELECT f.id, u.username FROM friendships f
            JOIN users u ON u.id = f.addressee_id
            WHERE f.requester_id = %s AND f.status = 'pending'
            ORDER BY f.created_at DESC
            """,
            (me,),
        )
        outgoing = [{"friendship_id": r["id"], "username": r["username"]} for r in cur.fetchall()]

    return {"friends": friends, "incoming": incoming, "outgoing": outgoing}


@router.post("/friends/request")
def request_friend(body: FriendRequestIn, user: dict = Depends(current_user)):
    me = user["id"]
    target = body.username.strip()
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT id FROM users WHERE username = %s", (target,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="找不到這個帳號")
        other = row["id"]
        if other == me:
            raise HTTPException(status_code=400, detail="不能加自己")

        # 對方已寄邀請給我 → 直接成為好友
        cur.execute(
            "SELECT id, status FROM friendships WHERE requester_id = %s AND addressee_id = %s",
            (other, me),
        )
        rev = cur.fetchone()
        if rev:
            if rev["status"] != "accepted":
                cur.execute("UPDATE friendships SET status = 'accepted' WHERE id = %s", (rev["id"],))
            return {"status": "accepted"}

        # 我已寄過 / 已是好友
        cur.execute(
            "SELECT status FROM friendships WHERE requester_id = %s AND addressee_id = %s",
            (me, other),
        )
        mine = cur.fetchone()
        if mine:
            return {"status": mine["status"]}

        cur.execute(
            "INSERT INTO friendships (requester_id, addressee_id, status) VALUES (%s, %s, 'pending')",
            (me, other),
        )
    return {"status": "pending"}


@router.post("/friends/{friendship_id}/accept")
def accept_friend(friendship_id: int, user: dict = Depends(current_user)):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE friendships SET status = 'accepted' WHERE id = %s AND addressee_id = %s AND status = 'pending' RETURNING id",
            (friendship_id, user["id"]),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到這個邀請")
    return {"ok": True}


@router.delete("/friends/{friendship_id}")
def remove_friend(friendship_id: int, user: dict = Depends(current_user)):
    """拒絕邀請或移除好友(任一方皆可)。"""
    me = user["id"]
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM friendships WHERE id = %s AND (requester_id = %s OR addressee_id = %s) RETURNING id",
            (friendship_id, me, me),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到")
    return {"ok": True}


# ---------- 看好友資料(依對方權限過濾) ----------
@router.get("/friends/{friend_uid}/feed")
def friend_feed(
    friend_uid: int,
    date: Optional[str] = None,
    tz: Optional[str] = None,
    user: dict = Depends(current_user),
):
    if not _are_friends(user["id"], friend_uid):
        raise HTTPException(status_code=403, detail="你們還不是好友")

    with get_cursor() as cur:
        cur.execute("SELECT username FROM users WHERE id = %s", (friend_uid,))
        u = cur.fetchone()
    if not u:
        raise HTTPException(status_code=404, detail="找不到使用者")

    p = _prefs(friend_uid)
    zone = resolve_tz(tz)
    start, end, day_str = day_bounds(date, zone)
    out = {"username": u["username"], "date": day_str, "shares": p}

    if p["share_diet"]:
        ds = day_summary(friend_uid, start, end)
        out["summary"] = ds
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id, eaten_at, name, calories, protein_g, source, note
                FROM entries WHERE user_id = %s AND eaten_at >= %s AND eaten_at < %s
                ORDER BY eaten_at DESC
                """,
                (friend_uid, start, end),
            )
            out["entries"] = [serialize_entry(r, zone) for r in cur.fetchall()]
    elif p["share_mascot"]:
        out["mascot"] = mascot_only(day_summary(friend_uid, start, end))

    if p["share_recipes"]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id, name, servings, calories, protein_g, ingredients, steps, video_url
                FROM recipes WHERE user_id = %s ORDER BY updated_at DESC
                """,
                (friend_uid,),
            )
            out["recipes"] = [
                {
                    "id": r["id"], "name": r["name"],
                    "servings": float(r["servings"]) if r["servings"] is not None else None,
                    "calories": r["calories"],
                    "protein_g": float(r["protein_g"]) if r["protein_g"] is not None else None,
                    "ingredients": r["ingredients"] or "", "steps": r["steps"] or "",
                    "video_url": r["video_url"] or "",
                }
                for r in cur.fetchall()
            ]
    return out
