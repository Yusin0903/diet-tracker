"""auth.py 純函式單元測試:密碼雜湊、邀請碼檢查(不碰 DB)。"""
from app.security import hash_password, verify_password
from app.services.users import check_invite_code
from app.settings import settings


# ---------- 密碼雜湊 ----------
def test_hash_verify_roundtrip():
    h = hash_password("secret123")
    assert verify_password("secret123", h)


def test_hash_is_salted():
    # 同密碼兩次雜湊應不同(隨機 salt)
    assert hash_password("secret123") != hash_password("secret123")


def test_wrong_password_fails():
    h = hash_password("secret123")
    assert not verify_password("wrong", h)


def test_verify_handles_malformed_hash():
    assert not verify_password("x", "not-a-valid-hash")
    assert not verify_password("x", "")
    assert not verify_password("x", "a$b$c")  # 段數對但內容無效


def test_hash_format():
    h = hash_password("pw")
    algo, rounds, salt, digest = h.split("$")
    assert algo == "pbkdf2_sha256"
    assert int(rounds) > 0
    assert len(salt) == 32  # 16 bytes hex


# ---------- 邀請碼 ----------
def test_invite_code_accepts_configured(monkeypatch):
    monkeypatch.setattr(settings, "invite_codes_raw", "alpha,bravo")
    assert check_invite_code("alpha")
    assert check_invite_code("  bravo  ")  # 會 strip
    assert not check_invite_code("charlie")


def test_invite_code_closed_when_unset(monkeypatch):
    # 沒設定任何邀請碼 => 全部拒絕(預設關上,不可無腦註冊)
    monkeypatch.setattr(settings, "invite_codes_raw", "")
    assert not check_invite_code("anything")
    assert not check_invite_code("")
