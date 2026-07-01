"""端到端 API 測試(需要 Postgres)。

沒設 DATABASE_URL 時整檔自動跳過,方便在沒有 DB 的環境只跑純函式測試。
跑法:
    export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/diet
    pytest tests/test_api.py
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="需要 DATABASE_URL 才能跑 API 整合測試",
)


@pytest.fixture(scope="module")
def client():
    from app.settings import settings
    settings.invite_codes_raw = "testcode"  # 測試用邀請碼
    settings.secret_key = settings.secret_key or "test-secret-key"  # 啟動檢查需要
    from fastapi.testclient import TestClient
    from app import db
    from app.main import app

    with TestClient(app) as c:
        with db.get_cursor(commit=True) as cur:
            cur.execute(
                "TRUNCATE users, entries, foods, profiles, recipes, "
                "friendships, share_prefs, exercises RESTART IDENTITY CASCADE"
            )
        yield c


def _register(client, name, code="testcode"):
    r = client.post("/api/auth/register", json={
        "username": name, "password": "secret1", "invite_code": code})
    return r


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- 邀請碼 / 認證 ----------
def test_register_requires_valid_invite(client):
    assert _register(client, "bad", code="WRONG").status_code == 403
    r = _register(client, "alice")
    assert r.status_code == 200
    assert "token" in r.json()


def test_duplicate_username(client):
    _register(client, "dup")
    assert _register(client, "dup").status_code == 409


def test_endpoints_require_auth(client):
    assert client.get("/api/summary").status_code in (401, 403)
    assert client.get("/api/foods").status_code in (401, 403)


def test_login_wrong_password(client):
    _register(client, "loginuser")
    r = client.post("/api/auth/login",
                    json={"username": "loginuser", "password": "nope"})
    assert r.status_code == 401


# ---------- 沒 profile:只顯示熱量 ----------
def test_summary_without_profile(client):
    tok = _register(client, "noprof").json()["token"]
    s = client.get("/api/summary", headers=_auth(tok)).json()
    assert s["has_profile"] is False
    assert s["targets"] is None
    assert s["consumed"] == {"calories": 0, "protein_g": 0.0}


def test_seed_foods_present(client):
    tok = _register(client, "seeded").json()["token"]
    foods = client.get("/api/foods", headers=_auth(tok)).json()
    assert len(foods) == 3  # config.SEED_FOODS


# ---------- entries + summary ----------
def test_barcode_source_accepted(client):
    tok = _register(client, "barcoder").json()["token"]
    h = _auth(tok)
    r = client.post("/api/entries", headers=h, json={
        "name": "可樂 330ml", "calories": 139, "protein_g": 0,
        "source": "barcode"})
    assert r.status_code == 200
    assert r.json()["source"] == "barcode"


def test_bad_source_rejected(client):
    tok = _register(client, "badsrc").json()["token"]
    h = _auth(tok)
    r = client.post("/api/entries", headers=h, json={
        "name": "x", "calories": 1, "protein_g": 0, "source": "telepathy"})
    assert r.status_code == 400


def test_entries_update_summary(client):
    tok = _register(client, "eater").json()["token"]
    h = _auth(tok)
    client.post("/api/entries", headers=h, json={
        "name": "便當", "calories": 600, "protein_g": 35, "source": "manual"})
    s = client.get("/api/summary", headers=h).json()
    assert s["consumed"]["calories"] == 600
    assert s["consumed"]["protein_g"] == 35.0


# ---------- profile -> TDEE / overflow ----------
def test_profile_drives_tdee_and_overflow(client):
    tok = _register(client, "tdee").json()["token"]
    h = _auth(tok)
    client.put("/api/profile", headers=h, json={
        "mode": "auto", "sex": "male", "age": 30, "height_cm": 178,
        "weight_kg": 80, "activity_level": "moderate", "goal": "cut"})
    s = client.get("/api/summary", headers=h).json()
    assert s["has_profile"] is True
    assert s["targets"]["tdee"] == 2740
    assert s["cap"] == 2740
    assert s["status"]["tdee"] == "within"
    # 吃爆 TDEE
    client.post("/api/entries", headers=h, json={
        "name": "buffet", "calories": 3000, "protein_g": 100, "source": "manual"})
    s2 = client.get("/api/summary", headers=h).json()
    assert s2["status"]["tdee"] == "over"
    assert s2["remaining"]["calories_to_tdee"] == 2740 - 3000


def test_manual_profile_caps_at_calories_max(client):
    tok = _register(client, "manualp").json()["token"]
    h = _auth(tok)
    client.put("/api/profile", headers=h, json={
        "mode": "manual", "calories_min": 1700,
        "calories_max": 1900, "protein_min": 150})
    s = client.get("/api/summary", headers=h).json()
    assert s["targets"]["tdee"] is None
    assert s["cap"] == 1900  # 無 TDEE 時退回熱量上限


# ---------- 跨使用者隔離 ----------
def test_user_isolation(client):
    ta = _register(client, "iso_a").json()["token"]
    tb = _register(client, "iso_b").json()["token"]
    eid = client.post("/api/entries", headers=_auth(ta), json={
        "name": "a的餐", "calories": 500, "protein_g": 20,
        "source": "manual"}).json()["id"]
    # b 看不到 a 的記錄
    assert client.get("/api/entries", headers=_auth(tb)).json() == []
    # b 刪不掉 a 的記錄
    assert client.delete(f"/api/entries/{eid}", headers=_auth(tb)).status_code == 404
    # a 自己刪得掉
    assert client.delete(f"/api/entries/{eid}", headers=_auth(ta)).status_code == 200


# ---------- 時區 ----------
def test_entry_edit(client):
    tok = _register(client, "editor").json()["token"]
    h = _auth(tok)
    eid = client.post("/api/entries", headers=h, json={
        "name": "便當", "calories": 600, "protein_g": 30, "source": "manual"}).json()["id"]
    r = client.put(f"/api/entries/{eid}", headers=h, json={
        "name": "雞腿便當", "calories": 720, "protein_g": 34, "note": "加蛋"})
    assert r.status_code == 200
    assert r.json()["name"] == "雞腿便當"
    s = client.get("/api/summary", headers=h).json()
    assert s["consumed"]["calories"] == 720
    # 別人改不到
    tok2 = _register(client, "editor2").json()["token"]
    r2 = client.put(f"/api/entries/{eid}", headers=_auth(tok2), json={
        "name": "x", "calories": 1, "protein_g": 0})
    assert r2.status_code == 404


def test_recipes_crud_and_isolation(client):
    tok = _register(client, "cook").json()["token"]
    h = _auth(tok)
    assert client.get("/api/recipes", headers=h).json() == []
    rid = client.post("/api/recipes", headers=h, json={
        "name": "雞胸蓋飯", "calories": 520, "protein_g": 48, "servings": 1,
        "ingredients": "雞胸 200g\n白飯 1 碗", "steps": "煎熟\n鋪上",
        "video_url": "https://youtu.be/abcdefghijk"}).json()["id"]
    lst = client.get("/api/recipes", headers=h).json()
    assert len(lst) == 1 and lst[0]["name"] == "雞胸蓋飯"
    assert lst[0]["video_url"] == "https://youtu.be/abcdefghijk"
    # 更新
    up = client.put(f"/api/recipes/{rid}", headers=h, json={
        "name": "辣雞胸蓋飯", "calories": 540, "protein_g": 48,
        "servings": 1, "ingredients": "雞胸 200g", "steps": "煎熟"})
    assert up.status_code == 200 and up.json()["name"] == "辣雞胸蓋飯"
    # 記一份到 entries
    le = client.post("/api/entries", headers=h, json={
        "name": "辣雞胸蓋飯", "calories": 540, "protein_g": 48, "source": "recipe"})
    assert le.status_code == 200 and le.json()["source"] == "recipe"
    # 跨使用者看不到也刪不掉
    tok2 = _register(client, "cook2").json()["token"]
    assert client.get("/api/recipes", headers=_auth(tok2)).json() == []
    assert client.delete(f"/api/recipes/{rid}", headers=_auth(tok2)).status_code == 404
    assert client.delete(f"/api/recipes/{rid}", headers=h).status_code == 200


def test_stats_range(client):
    tok = _register(client, "trend").json()["token"]
    h = _auth(tok)
    client.post("/api/entries", headers=h, json={
        "name": "餐", "calories": 700, "protein_g": 40, "source": "manual"})
    # 取含今天的 3 天區間
    import datetime as _dt
    today = _dt.date.today()
    start = (today - _dt.timedelta(days=2)).isoformat()
    end = today.isoformat()
    r = client.get(f"/api/stats?start={start}&end={end}", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert len(data["days"]) == 3            # 區間補滿
    assert data["days"][-1]["date"] == end   # 最後一天是今天
    assert data["days"][-1]["calories"] == 700
    assert data["days"][0]["calories"] == 0  # 沒記錄的填 0


def test_stats_bad_range(client):
    tok = _register(client, "trend2").json()["token"]
    h = _auth(tok)
    assert client.get("/api/stats?start=2026-01-05&end=2026-01-01", headers=h).status_code == 400


def test_friends_flow_and_permissions(client):
    ta = _register(client, "amy").json()["token"]; ha = _auth(ta)
    tb = _register(client, "ben").json()["token"]; hb = _auth(tb)
    tc = _register(client, "cara").json()["token"]; hc = _auth(tc)
    # amy 加 ben
    assert client.post("/api/friends/request", headers=ha, json={"username": "ben"}).json()["status"] == "pending"
    # ben 看到 incoming,接受
    inc = client.get("/api/friends", headers=hb).json()["incoming"]
    assert len(inc) == 1
    fid = inc[0]["friendship_id"]
    assert client.post(f"/api/friends/{fid}/accept", headers=hb).status_code == 200
    # 雙方都成為好友
    fa = client.get("/api/friends", headers=ha).json()["friends"]
    assert len(fa) == 1 and fa[0]["username"] == "ben"
    fb = client.get("/api/friends", headers=hb).json()["friends"]
    amy_uid = fb[0]["user_id"]

    # amy 記一筆 + 開「飲食記錄」分享
    client.post("/api/entries", headers=ha, json={"name": "便當", "calories": 700, "protein_g": 40, "source": "manual"})
    client.put("/api/share", headers=ha, json={"share_mascot": True, "share_diet": True, "share_recipes": False})
    feed = client.get(f"/api/friends/{amy_uid}/feed", headers=hb).json()
    assert feed["shares"]["share_diet"] is True
    assert feed["summary"]["consumed"]["calories"] == 700
    assert any(e["name"] == "便當" for e in feed["entries"])

    # amy 改成只分享熊狀態 → ben 看不到數字/明細,只有 mascot
    client.put("/api/share", headers=ha, json={"share_mascot": True, "share_diet": False, "share_recipes": False})
    feed2 = client.get(f"/api/friends/{amy_uid}/feed", headers=hb).json()
    assert "entries" not in feed2 and "summary" not in feed2
    assert feed2["mascot"]["state"] in ("blue", "green", "amber", "red")

    # cara 不是好友 → 看不到
    assert client.get(f"/api/friends/{amy_uid}/feed", headers=hc).status_code == 403


def test_timezone_param(client):
    tok = _register(client, "tz").json()["token"]
    h = _auth(tok)
    # 無效時區退回台北、仍 200
    assert client.get("/api/summary?tz=bogus", headers=h).status_code == 200
    # 合法時區回傳 YYYY-MM-DD
    d = client.get("/api/summary?tz=America/New_York", headers=h).json()["date"]
    assert len(d) == 10 and d[4] == "-"


# ---------- 運動記錄 ----------
def test_exercise_calories_default_weight(client):
    # 沒設定個人資料:用預設體重 65kg。9.75km/h 的配速(5.2km/32min)算跑步 ACSM 公式,
    # MET = (0.2*162.5+3.5)/3.5 ≈ 10.286,kcal = 10.286*65*32/60 ≈ 357
    tok = _register(client, "runner_noprofile").json()["token"]
    h = _auth(tok)
    r = client.post("/api/exercises", headers=h, json={
        "ex_type": "running", "duration_min": 32, "distance_km": 5.2})
    assert r.status_code == 200
    body = r.json()
    assert body["calories"] == 357
    assert body["ex_type"] == "running"
    assert body["distance_km"] == 5.2


def test_exercise_calories_slow_pace_uses_walking_formula(client):
    # 20 分鐘跑(選)1 公里 = 時速僅 3km/h,遠低於「跑步」門檻(6.4km/h),
    # 應該退回走路公式估算,而不是死套跑步的高 MET(用戶回報這樣算出 198 kcal 明顯過高)。
    # MET = (0.1*50+3.5)/3.5 ≈ 2.4286,kcal = 2.4286*65*20/60 ≈ 53(預設體重 65kg)
    tok = _register(client, "slow_jogger").json()["token"]
    h = _auth(tok)
    r = client.post("/api/exercises", headers=h, json={
        "ex_type": "running", "duration_min": 20, "distance_km": 1})
    assert r.status_code == 200
    assert r.json()["calories"] == 53


def test_exercise_calories_walking_and_cycling_use_speed(client):
    tok = _register(client, "speedy").json()["token"]
    h = _auth(tok)
    # 走路 2km/30min = 4km/h → MET=(0.1*66.667+3.5)/3.5≈2.905,kcal≈65*2.905*0.5≈94
    w = client.post("/api/exercises", headers=h, json={
        "ex_type": "walking", "duration_min": 30, "distance_km": 2}).json()
    assert w["calories"] == 94
    # 單車 20km/60min = 20km/h → 落在 19–22.4km/h 區間,MET=8.0,kcal=65*8*1=520
    c = client.post("/api/exercises", headers=h, json={
        "ex_type": "cycling", "duration_min": 60, "distance_km": 20}).json()
    assert c["calories"] == 520


def test_exercise_calories_no_distance_falls_back_to_flat_met(client):
    # 沒填距離:退回固定 MET(維持原本行為),重訓 5.0 MET * 65kg * 45/60 hr ≈ 244
    tok = _register(client, "no_distance").json()["token"]
    h = _auth(tok)
    r = client.post("/api/exercises", headers=h, json={
        "ex_type": "running", "duration_min": 30})
    assert r.status_code == 200
    assert r.json()["calories"] == round(7.0 * 65 * 0.5)


def test_exercise_calories_uses_profile_weight(client):
    # 有個人資料:用自己的體重估算。5.0 MET * 80kg * 45/60 hr = 300 kcal
    tok = _register(client, "lifter").json()["token"]
    h = _auth(tok)
    client.put("/api/profile", headers=h, json={
        "mode": "auto", "sex": "male", "age": 30, "height_cm": 178,
        "weight_kg": 80, "activity_level": "moderate", "goal": "maintain"})
    r = client.post("/api/exercises", headers=h, json={
        "ex_type": "strength", "duration_min": 45})
    assert r.status_code == 200
    assert r.json()["calories"] == 300
    assert r.json()["distance_km"] is None


def test_exercise_bad_type_rejected(client):
    tok = _register(client, "badtype").json()["token"]
    h = _auth(tok)
    r = client.post("/api/exercises", headers=h, json={
        "ex_type": "telepathy", "duration_min": 10})
    assert r.status_code == 422


def test_exercise_list_month_and_delete(client):
    tok = _register(client, "mover").json()["token"]
    h = _auth(tok)
    e1 = client.post("/api/exercises", headers=h, json={
        "ex_type": "yoga", "duration_min": 20}).json()
    client.post("/api/exercises", headers=h, json={
        "ex_type": "walking", "duration_min": 30, "distance_km": 2.5})

    import datetime as _dt
    today = _dt.date.today()

    day = client.get("/api/exercises", headers=h).json()
    assert day["date"] == today.isoformat()
    assert len(day["items"]) == 2
    assert day["total_duration_min"] == 50

    month = client.get(f"/api/exercises/month?year={today.year}&month={today.month}", headers=h).json()
    assert today.isoformat() in month["days"]
    assert month["streak"] >= 1

    # 跨使用者隔離
    tok2 = _register(client, "mover2").json()["token"]
    assert client.get("/api/exercises", headers=_auth(tok2)).json()["items"] == []
    assert client.delete(f"/api/exercises/{e1['id']}", headers=_auth(tok2)).status_code == 404

    # 自己刪得掉
    assert client.delete(f"/api/exercises/{e1['id']}", headers=h).status_code == 200
    day2 = client.get("/api/exercises", headers=h).json()
    assert len(day2["items"]) == 1


def test_strength_movements_and_sets(client):
    tok = _register(client, "gymrat").json()["token"]
    h = _auth(tok)
    ex = client.post("/api/exercises", headers=h, json={
        "ex_type": "strength", "duration_min": 45}).json()
    eid = ex["id"]

    assert client.get(f"/api/exercises/{eid}/movements", headers=h).json() == []

    mv = client.post(f"/api/exercises/{eid}/movements", headers=h, json={"name": "槓鈴臥推"}).json()
    assert mv["name"] == "槓鈴臥推" and mv["sets"] == []
    mid = mv["id"]

    s1 = client.post(f"/api/exercises/movements/{mid}/sets", headers=h, json={
        "weight_kg": 40, "reps": 12}).json()
    client.post(f"/api/exercises/movements/{mid}/sets", headers=h, json={"weight_kg": 45, "reps": 10})

    movements = client.get(f"/api/exercises/{eid}/movements", headers=h).json()
    assert len(movements) == 1
    assert len(movements[0]["sets"]) == 2
    assert movements[0]["sets"][0] == {"id": s1["id"], "weight_kg": 40.0, "reps": 12}

    # 編輯一組
    upd = client.put(f"/api/exercises/sets/{s1['id']}", headers=h, json={
        "weight_kg": 42.5, "reps": 11})
    assert upd.status_code == 200 and upd.json()["weight_kg"] == 42.5

    # 熱量不受組數/次數影響,仍是建立時依時長算好的值
    assert client.get(f"/api/exercises", headers=h).json()["items"][0]["calories"] == ex["calories"]

    # 刪一組
    assert client.delete(f"/api/exercises/sets/{s1['id']}", headers=h).status_code == 200
    assert len(client.get(f"/api/exercises/{eid}/movements", headers=h).json()[0]["sets"]) == 1

    # 刪動作(連帶清掉剩下的組)
    assert client.delete(f"/api/exercises/movements/{mid}", headers=h).status_code == 200
    assert client.get(f"/api/exercises/{eid}/movements", headers=h).json() == []

    # 跨使用者隔離:別人動不到我的動作/組數/運動記錄
    tok2 = _register(client, "gymrat2").json()["token"]
    h2 = _auth(tok2)
    mv2 = client.post(f"/api/exercises/{eid}/movements", headers=h, json={"name": "深蹲"}).json()
    s2 = client.post(f"/api/exercises/movements/{mv2['id']}/sets", headers=h, json={
        "weight_kg": 60, "reps": 8}).json()
    assert client.get(f"/api/exercises/{eid}/movements", headers=h2).status_code == 404
    assert client.post(f"/api/exercises/{eid}/movements", headers=h2, json={"name": "x"}).status_code == 404
    assert client.post(f"/api/exercises/movements/{mv2['id']}/sets", headers=h2, json={
        "reps": 5}).status_code == 404
    assert client.put(f"/api/exercises/sets/{s2['id']}", headers=h2, json={"reps": 5}).status_code == 404
    assert client.delete(f"/api/exercises/sets/{s2['id']}", headers=h2).status_code == 404
    assert client.delete(f"/api/exercises/movements/{mv2['id']}", headers=h2).status_code == 404
