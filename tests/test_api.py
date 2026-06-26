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
                "TRUNCATE users, entries, foods, profiles RESTART IDENTITY CASCADE"
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
def test_timezone_param(client):
    tok = _register(client, "tz").json()["token"]
    h = _auth(tok)
    # 無效時區退回台北、仍 200
    assert client.get("/api/summary?tz=bogus", headers=h).status_code == 200
    # 合法時區回傳 YYYY-MM-DD
    d = client.get("/api/summary?tz=America/New_York", headers=h).json()["date"]
    assert len(d) == 10 and d[4] == "-"
