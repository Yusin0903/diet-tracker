"""集中設定:環境變數、每日目標、邀請碼。

所有設定都從這裡讀,避免散落各處。
"""
import os
from zoneinfo import ZoneInfo

# --- 時區 ---------------------------------------------------------------
# 「今天」一律以台北時區(UTC+8)的自然日為界。
TZ_NAME = os.environ.get("TZ", "Asia/Taipei")
TAIPEI = ZoneInfo("Asia/Taipei")

# --- 資料庫 -------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# --- Gemini -------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# --- 認證 ---------------------------------------------------------------
# JWT 簽章用密鑰,正式環境務必設一組長亂數。
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")
# Token 有效天數
TOKEN_TTL_DAYS = int(os.environ.get("TOKEN_TTL_DAYS", "30"))

# --- 邀請碼 -------------------------------------------------------------
# 用逗號分隔多組邀請碼。沒有有效邀請碼就不能註冊(不能無腦註冊)。
# 安全重點:用「高熵」隨機碼,不要用好記的單字+年份(會被字典暴力試出來)。
#   產生方式:openssl rand -hex 16   → 例如 INVITE_CODES="3f9a...c1"
INVITE_CODES = {
    code.strip()
    for code in os.environ.get("INVITE_CODES", "").split(",")
    if code.strip()
}

# --- 速率限制(擋邀請碼/密碼暴力嘗試) -------------------------------
# 同一來源 IP 在 window 秒內失敗達 max 次,就鎖 block 秒(回 429)。
# 單機部署用記憶體計數即可;多副本日後可換成 Redis 之類的共享儲存。
REG_MAX_FAILURES = int(os.environ.get("REG_MAX_FAILURES", "8"))
REG_WINDOW_S = int(os.environ.get("REG_WINDOW_S", "600"))      # 10 分鐘
REG_BLOCK_S = int(os.environ.get("REG_BLOCK_S", "1800"))       # 鎖 30 分鐘
LOGIN_MAX_FAILURES = int(os.environ.get("LOGIN_MAX_FAILURES", "10"))
LOGIN_WINDOW_S = int(os.environ.get("LOGIN_WINDOW_S", "600"))
LOGIN_BLOCK_S = int(os.environ.get("LOGIN_BLOCK_S", "900"))    # 鎖 15 分鐘

# --- 每日目標(cut 期) -------------------------------------------------
# 日後要調就改這裡或用環境變數覆蓋。
TARGETS = {
    "calories_min": int(os.environ.get("CALORIES_MIN", "1700")),
    "calories_max": int(os.environ.get("CALORIES_MAX", "1900")),
    "protein_min": int(os.environ.get("PROTEIN_MIN", "150")),
}

# --- 初始常用食物(每位新會員註冊時各帶一份) -------------------------
SEED_FOODS = [
    {"name": "雞胸便當(431cal 那款)", "calories": 431, "protein_g": 38.0},
    {"name": "乳清一杯", "calories": 150, "protein_g": 27.0},
    {"name": "6吋雞肉潛艇堡", "calories": 325, "protein_g": 20.0},
]
