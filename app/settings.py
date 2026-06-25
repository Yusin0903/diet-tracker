"""集中設定:用 pydantic-settings 從環境變數讀取。

所有設定都集中在 Settings,避免散落各處。
"""
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 「今天」的預設時區後備值(實際以前端帶上的使用者時區為主)。
TAIPEI = ZoneInfo("Asia/Taipei")

# 每位新會員註冊時帶的通用範例常用食物(皆可自行刪改)。
SEED_FOODS = [
    {"name": "白飯(一碗)", "calories": 280, "protein_g": 5.5},
    {"name": "雞胸肉(100g)", "calories": 165, "protein_g": 31.0},
    {"name": "乳清蛋白(一匙)", "calories": 120, "protein_g": 24.0},
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 資料庫
    database_url: str = ""
    db_max_conn: int = 40  # 需 >= FastAPI 同步端點的執行緒併發數

    # Gemini(只放後端)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # 認證
    secret_key: str = "dev-insecure-change-me"
    token_ttl_days: int = 30

    # 邀請碼(逗號分隔;沒有有效邀請碼就不能註冊)
    invite_codes_raw: str = Field("", validation_alias="INVITE_CODES")

    # 速率限制(擋暴力嘗試)
    reg_max_failures: int = 8
    reg_window_s: int = 600
    reg_block_s: int = 1800
    login_max_failures: int = 10
    login_window_s: int = 600
    login_block_s: int = 900

    # 時區後備值
    tz: str = "Asia/Taipei"

    @property
    def invite_codes(self) -> set[str]:
        return {c.strip() for c in self.invite_codes_raw.split(",") if c.strip()}


settings = Settings()
