-- 會員
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    invite_code   TEXT,                    -- 註冊時用的邀請碼(留存備查)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 每位會員的每日目標設定(由規格估算或手動填,沒有則用系統預設)
CREATE TABLE IF NOT EXISTS profiles (
    user_id        INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    mode           TEXT NOT NULL DEFAULT 'auto',   -- 'auto' | 'manual'
    sex            TEXT,                            -- 'male' | 'female'
    age            INTEGER,
    height_cm      NUMERIC(5,1),
    weight_kg      NUMERIC(5,1),
    body_fat_pct   NUMERIC(4,1),                    -- 體脂率(可選,有就用 Katch-McArdle)
    measured_bmr   INTEGER,                         -- 量測報告直接給的 BMR(可選,最準)
    activity_level TEXT,
    goal           TEXT,                            -- 'cut' | 'maintain' | 'bulk'
    calorie_adjust INTEGER,                         -- 對 TDEE 的熱量調整(可選,覆蓋預設)
    tdee           INTEGER,                         -- 估出的 TDEE(吉祥物「滿出來」的基準;manual 模式可為 NULL)
    calories_min   INTEGER NOT NULL,
    calories_max   INTEGER NOT NULL,
    protein_min    INTEGER NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 一筆飲食記錄
CREATE TABLE IF NOT EXISTS entries (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    eaten_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    name        TEXT NOT NULL,           -- 食物名稱
    calories    INTEGER NOT NULL,        -- 熱量 kcal
    protein_g   NUMERIC(5,1) NOT NULL,   -- 蛋白質 g
    source      TEXT NOT NULL,           -- 'photo' | 'manual' | 'favorite'
    note        TEXT,                    -- 備註(可選)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_entries_user_eaten ON entries (user_id, eaten_at);

-- 常用食物(便當、潛艇堡、蛋白粉…),每位會員各自一份
CREATE TABLE IF NOT EXISTS foods (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    calories    INTEGER NOT NULL,
    protein_g   NUMERIC(5,1) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, name)
);

-- 自己記的食譜,每位會員各自一份
CREATE TABLE IF NOT EXISTS recipes (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    servings     NUMERIC(5,1),            -- 整份食譜產出幾份(可選)
    calories     INTEGER,                 -- 每份熱量(可選)
    protein_g    NUMERIC(6,1),            -- 每份蛋白(可選)
    ingredients  TEXT,                    -- 食材,一行一項
    steps        TEXT,                    -- 步驟,一行一步
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_recipes_user ON recipes (user_id, updated_at DESC);
