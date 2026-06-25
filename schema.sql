-- 會員
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    invite_code   TEXT,                    -- 註冊時用的邀請碼(留存備查)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
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
