# 飲控 App 🥗

**繁體中文** · [English](README.md)

自用的飲食記錄工具:**快速記錄 + 自動加總對照每日目標**。拍食物照讓 Gemini 估熱量/蛋白、手動輸入、或從常用食物一鍵記錄,首頁一眼看「今天吃了多少 / 還剩多少」。

加了**會員系統**:需要**邀請碼**才能註冊(不能無腦註冊),登入後資料各自獨立。

## 技術選型

| 層 | 技術 |
|---|---|
| 後端 | Python + FastAPI |
| 資料庫 | Postgres(`DATABASE_URL` 連線) |
| 前端 | PWA(可加到主畫面、相機拍照) |
| AI | Gemini 2.5 Flash(vision,JSON 輸出) |
| 部署 | Zeabur |

> **GEMINI_API_KEY 與邀請碼只放後端,從環境變數讀取,絕不進前端。**

## 專案結構

```
diet-tracker/
├── app/                      # FastAPI 應用套件
│   ├── main.py               # 組裝 app:lifespan、include routers、mount 靜態檔
│   ├── settings.py           # pydantic-settings 設定(環境變數、seed 食物)
│   ├── db.py                 # Postgres 連線池、建表
│   ├── security.py           # 密碼雜湊、JWT、current_user 依賴
│   ├── rate_limit.py         # per-IP 速率限制(擋暴力嘗試)
│   ├── deps.py               # 時區解析、日界線、entry 序列化
│   ├── schemas.py            # Pydantic 請求模型
│   ├── sql/schema.sql        # users / profiles / entries / foods
│   ├── routers/              # 各資源一個 APIRouter
│   │   ├── auth.py           # /api/auth(註冊/登入/me)
│   │   ├── analyze.py        # /api/analyze
│   │   ├── entries.py        # /api/entries
│   │   ├── summary.py        # /api/summary
│   │   ├── foods.py          # /api/foods
│   │   └── profile.py        # /api/profile
│   └── services/             # 商業邏輯
│       ├── users.py          # 註冊/登入/邀請碼
│       ├── profile.py        # 目標讀寫
│       ├── targets.py        # TDEE / 熱量 / 蛋白估算
│       └── gemini.py         # Gemini 2.5 Flash vision
├── frontend/                 # PWA(static):index.html / app.js / styles.css / sw.js / icons
├── tests/                    # pytest(targets / ratelimit / auth / api)
├── requirements.txt
├── Dockerfile
└── .env.example
```

## 環境變數

| 變數 | 必填 | 說明 |
|---|---|---|
| `DATABASE_URL` | ✅ | Postgres 連線字串 |
| `GEMINI_API_KEY` | ✅(要用拍照辨識) | Gemini API key |
| `GEMINI_MODEL` | | 預設 `gemini-2.5-flash` |
| `INVITE_CODES` | ✅ | 逗號分隔的邀請碼,**沒設就沒人能註冊** |
| `SECRET_KEY` | ✅ | JWT 簽章密鑰,用 `openssl rand -hex 32` 產生 |
| `TOKEN_TTL_DAYS` | | 登入有效天數,預設 30 |
| `TZ` | | 預設 `Asia/Taipei` |

> 每日目標已改為每位會員自行設定(填規格估 TDEE 或手動輸入),不再用環境變數。

### 「今天」的時區

前端會用 `Intl` **自動偵測每位使用者裝置的時區**,隨 API 帶給後端,「今天」的日界線就依各自時區計算(後端沒收到或無效時退回 `Asia/Taipei`)。所以人在不同時區的會員,跨日不會記錯天。`TZ` 環境變數只當作後端的預設後備值。

## 本地開發

```bash
# 1. 準備 Postgres(本機或 Docker)
docker run -d --name diet-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16

# 2. 設定環境變數
cp .env.example .env        # 編輯填入 GEMINI_API_KEY、INVITE_CODES、SECRET_KEY
export $(grep -v '^#' .env | xargs)
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres

# 3. 裝套件並啟動
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

開 http://localhost:8000 →「註冊」分頁,用 `INVITE_CODES` 裡的任一組邀請碼註冊。
建表與 seed 常用食物會在啟動 / 註冊時自動完成。

## 測試

```bash
pip install -r requirements.txt
pytest                 # 純函式測試(targets/ratelimit/auth)免 DB
# 要連同 API 整合測試一起跑,設好 DATABASE_URL(會 TRUNCATE 該庫的表):
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/diet
pytest
```

沒設 `DATABASE_URL` 時,需要資料庫的 API 測試會自動跳過,純邏輯測試照跑。

## API

| Method | Path | 說明 |
|---|---|---|
| POST | `/api/auth/register` | `{username, password, invite_code}` → `{token, username}` |
| POST | `/api/auth/login` | `{username, password}` → `{token, username}` |
| GET | `/api/auth/me` | 驗證 token |
| POST | `/api/analyze` | 上傳圖片(multipart),回 Gemini 估值,**不寫 DB** |
| POST | `/api/entries` | 寫入一筆記錄 |
| GET | `/api/entries?date=YYYY-MM-DD` | 查某日記錄(預設今天,台北時區) |
| DELETE | `/api/entries/{id}` | 刪一筆 |
| GET | `/api/summary?date=YYYY-MM-DD` | 當日加總 + 對照目標(含 `has_profile`、`tdee`、`cap`) |
| GET | `/api/profile` | 取得會員的身體數據 / 目標 |
| POST | `/api/profile/preview` | 試算 TDEE 與目標(**不存檔**) |
| PUT | `/api/profile` | 儲存身體數據,計算並存下 TDEE 與目標 |
| GET / POST | `/api/foods` | 常用食物清單 / 新增 |
| DELETE | `/api/foods/{id}` | 刪常用食物 |

除 `register`/`login` 外,所有 `/api` 都需帶 `Authorization: Bearer <token>`。

`/api/analyze` 只把「圖片 → 估值」回給前端,使用者**確認/修改後**才呼叫 `/api/entries` 寫入 —— AI 的誤差由人把關。

## Zeabur 部署

1. **開 Postgres**:Zeabur 專案 → Marketplace → 一鍵開 PostgreSQL。
2. **加後端 service**:從這個 GitHub repo 部署。Zeabur 會偵測到 `Dockerfile`(或 `requirements.txt`)。
3. **設環境變數**(後端 service):
   - `DATABASE_URL` → 引用 Postgres 的 `${postgres.DATABASE_URL}`
   - `GEMINI_API_KEY`、`GEMINI_MODEL`
   - `INVITE_CODES`(例:`alpha2026,bravo2026`)
   - `SECRET_KEY`(`openssl rand -hex 32`)
   - `TZ=Asia/Taipei`
4. Deploy。前端靜態檔由 FastAPI 直接 serve,不需另外開 service。
5. 開好的網址即可加到手機主畫面(PWA)。

## 邀請碼怎麼運作

- 註冊時必須帶 `INVITE_CODES` 裡的其中一組碼,否則回 `403 邀請碼無效`。
- 沒設定 `INVITE_CODES`(空值)時,**任何人都無法註冊**——預設就是關上的。
- 要再多放人進來就在環境變數加一組碼、重新部署即可。

### 防暴力破解(邀請碼/密碼)

兩道防線,缺一不可:

1. **高熵邀請碼(治本)**:用 `openssl rand -hex 16` 產生 32 字隨機碼,別用 `alpha2026`
   這類好記的單字+年份——後者用字典幾千次就試出來了。高熵碼讓「猜中」在數學上不可能。
2. **速率限制(治標)**:`/api/auth/register`、`/api/auth/login` 都做了 per-IP 滑動視窗限制。
   同一 IP 短時間內猜錯太多次就鎖定一段時間回 `429`,成功則清零、不影響正常使用者。
   門檻可用 `REG_*`、`LOGIN_*` 環境變數調整(見 `.env.example`)。
   - 走 Zeabur 反向代理時,真實 IP 從 `X-Forwarded-For` 取得。
   - 速率計數放在記憶體;單副本夠用,日後若水平擴展成多副本要改用 Redis 之類的共享儲存。

> 想更嚴格:把邀請碼改成「單次使用」(用掉就失效)、或加上每組碼的註冊人數上限,
> 都可以在 `app/services/users.py` 配一張 DB 表來做。自用情境通常高熵碼 + 速率限制就夠。

## 每日目標 & TDEE(每位會員各自計算)

目標不再寫死,而是**由每位會員的身體數據估出 TDEE** 再換算:

- **自動估算**:填性別/年齡/身高/體重/活動量/目標 → Mifflin-St Jeor 估 BMR × 活動係數 = TDEE。
- **體脂測量**:有體脂率(InBody/體脂計)→ 改用 **Katch-McArdle**(以淨體重估,較準),蛋白目標也用淨體重算;量測報告若直接給 BMR,可填入直接採用(最準)。
- **手動輸入**:已知自己目標的人,直接填熱量上下限與蛋白下限。

由 TDEE 與目標(`cut`/`maintain`/`bulk`)算出:熱量目標區間、蛋白目標、以及 **TDEE 上限**。

| 公式 | 何時用 |
|---|---|
| Mifflin-St Jeor | 只有基本規格時 |
| Katch-McArdle | 有體脂率時(較準) |
| 量測 BMR | 報告直接給 BMR(最準) |

活動係數:久坐 1.2 / 輕度 1.375 / 中度 1.55 / 高度 1.725 / 非常高 1.9。
目標調整:減脂 −400、維持 0、增肌 +250 kcal(可用 `calorie_adjust` 覆蓋)。

### 首頁可愛吉祥物

熱量視覺是一隻**圓滾滾吉祥物**,肚子像水位一樣隨當天吃的熱量往上填:

- 還沒到目標 → 藍色、半空。
- 進入熱量目標區間 → **變綠、亮達標光暈**。
- 超出目標但還沒到 TDEE → 橘色提醒。
- **超過 TDEE → 整隻變紅、鼓起來、頭頂溢出水滴、表情被塞爆**,並顯示「超過 TDEE ⬜ kcal」。

**沒設定身體數據的會員**:不評估目標,首頁就單純顯示今天吃了多少熱量,並提示去設定。
蛋白未達標一樣在首頁明顯警示(cut 期最關鍵的指標)。
