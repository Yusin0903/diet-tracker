# Diet Tracker 🥗

**English** · [繁體中文](README.zh-TW.md)

A diet-logging tool built around one core value: **log fast + auto-total against your daily goals**. Snap a food photo and let Gemini estimate calories/protein, scan a product barcode (looked up via Open Food Facts), type values in manually, or one-tap a favorite. The home screen shows at a glance "how much you've eaten today / how much room is left."

It has a **member system**: an **invite code** is required to register (no open sign-up), and each member's data is fully isolated.

## Screenshots

| Home (mascot vs. target) | Trend (week / month) | Recipe detail |
|---|---|---|
| <img src="docs/screenshots/home.png" width="240" alt="Home" /> | <img src="docs/screenshots/trends.png" width="240" alt="Trend" /> | <img src="docs/screenshots/recipe.png" width="240" alt="Recipe" /> |

The home mascot fills toward your TDEE and "overflows" when you go over; the trend tab charts daily calories against your target band; recipes are logged per serving.

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python + FastAPI |
| Database | Postgres (`DATABASE_URL`) |
| Frontend | PWA (add-to-home-screen, camera capture) |
| AI | Gemini 2.5 Flash (vision, JSON output) |
| Deploy | Zeabur |

> **`GEMINI_API_KEY` and invite codes live only on the backend, read from env — they never reach the frontend.**

## Project structure

```
diet-tracker/
├── app/                      # FastAPI application package
│   ├── main.py               # Assembles the app: lifespan, include routers, mount static
│   ├── settings.py           # pydantic-settings config (env vars, seed foods)
│   ├── db.py                 # Postgres connection pool, table init
│   ├── security.py           # Password hashing, JWT, current_user dependency
│   ├── rate_limit.py         # Per-IP rate limiter (brute-force protection)
│   ├── deps.py               # Timezone resolve, day bounds, entry serialization
│   ├── schemas.py            # Pydantic request models
│   ├── sql/schema.sql        # users / profiles / entries / foods
│   ├── routers/              # One APIRouter per resource
│   │   ├── auth.py           # /api/auth (register / login / me)
│   │   ├── analyze.py        # /api/analyze
│   │   ├── entries.py        # /api/entries
│   │   ├── summary.py        # /api/summary
│   │   ├── foods.py          # /api/foods
│   │   └── profile.py        # /api/profile
│   └── services/             # Business logic
│       ├── users.py          # register / login / invite codes
│       ├── profile.py        # target read/write
│       ├── targets.py        # TDEE / calorie / protein estimation
│       └── gemini.py         # Gemini 2.5 Flash vision
├── frontend/                 # PWA (static): index.html / app.js / styles.css / sw.js / icons
├── tests/                    # pytest (targets / ratelimit / auth / api)
├── requirements.txt
├── Dockerfile
└── .env.example
```

## Environment variables

| Var | Required | Notes |
|---|---|---|
| `DATABASE_URL` | ✅ | Postgres connection string |
| `GEMINI_API_KEY` | ✅ (for photo analysis) | Gemini API key |
| `GEMINI_MODEL` | | Defaults to `gemini-2.5-flash` |
| `INVITE_CODES` | ✅ | Comma-separated invite codes; **unset = nobody can register** |
| `SECRET_KEY` | ✅ | JWT signing key, generate with `openssl rand -hex 32` |
| `TOKEN_TTL_DAYS` | | Login validity in days, defaults to 30 |
| `TZ` | | Defaults to `Asia/Taipei` |

> Daily targets are no longer set via env — each member configures their own (estimate TDEE from specs, or enter manually).

### What counts as "today" (timezone)

The frontend uses `Intl` to **auto-detect each user's device timezone** and passes it to the API, so the day boundary is computed in each user's own zone (the backend falls back to `Asia/Taipei` if it's missing or invalid). Members in different timezones won't log on the wrong day. The `TZ` env var is only the backend's fallback default.

## Local development

```bash
# 1. Start Postgres (locally or via Docker)
docker run -d --name diet-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16

# 2. Configure environment
cp .env.example .env        # fill in GEMINI_API_KEY, INVITE_CODES, SECRET_KEY
export $(grep -v '^#' .env | xargs)
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres

# 3. Install deps and run
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 → "Register" tab, and sign up with any code from `INVITE_CODES`.
Tables and seed favorites are created automatically on startup / registration.

## Tests

```bash
pip install -r requirements.txt
pytest                 # pure-function tests (targets/ratelimit/auth), no DB needed
# To also run the API integration tests, set DATABASE_URL (it TRUNCATEs that DB's tables):
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/diet
pytest
```

Without `DATABASE_URL`, the DB-backed API tests auto-skip and the pure-logic tests still run.

## API

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/register` | `{username, password, invite_code}` → `{token, username}` |
| POST | `/api/auth/login` | `{username, password}` → `{token, username}` |
| GET | `/api/auth/me` | Validate token |
| POST | `/api/analyze` | Upload an image (multipart), returns Gemini estimate, **does not write to DB** |
| POST | `/api/entries` | Create one entry |
| GET | `/api/entries?date=YYYY-MM-DD` | List a day's entries (defaults to today, user timezone) |
| DELETE | `/api/entries/{id}` | Delete one entry |
| GET | `/api/summary?date=YYYY-MM-DD` | Daily totals vs. targets (incl. `has_profile`, `tdee`, `cap`) |
| GET | `/api/profile` | Get the member's body data / targets |
| POST | `/api/profile/preview` | Estimate TDEE & targets (**no write**) |
| PUT | `/api/profile` | Save body data, compute & store TDEE and targets |
| GET / POST | `/api/foods` | Favorite foods list / create |
| DELETE | `/api/foods/{id}` | Delete a favorite |

Every `/api` route except `register`/`login` requires `Authorization: Bearer <token>`.

`/api/analyze` only returns the "image → estimate" to the frontend; the user **confirms/edits**, then `/api/entries` writes it — a human checks the AI's error.

## Deploying to Zeabur

1. **Add Postgres**: Zeabur project → Marketplace → one-click PostgreSQL.
2. **Add the backend service**: deploy from this GitHub repo. Zeabur detects the `Dockerfile` (or `requirements.txt`).
3. **Set environment variables** (backend service):
   - `DATABASE_URL` → reference Postgres's `${postgres.DATABASE_URL}`
   - `GEMINI_API_KEY`, `GEMINI_MODEL`
   - `INVITE_CODES` (e.g. `alpha2026,bravo2026`)
   - `SECRET_KEY` (`openssl rand -hex 32`)
   - `TZ=Asia/Taipei`
4. Deploy. The frontend static files are served directly by FastAPI — no separate service needed.
5. The resulting URL can be added to a phone's home screen (PWA).

## How invite codes work

- Registration requires one of the codes in `INVITE_CODES`, otherwise it returns `403 invalid invite code`.
- When `INVITE_CODES` is unset (empty), **nobody can register** — closed by default.
- To let more people in, add a code to the env var and redeploy.

### Brute-force protection (invite codes / passwords)

Two layers, both needed:

1. **High-entropy invite codes (the real fix)**: generate a 32-char random code with `openssl rand -hex 16`, not a guessable `alpha2026`-style word+year — the latter falls to a dictionary in a few thousand tries. A high-entropy code makes guessing mathematically infeasible.
2. **Rate limiting (the safety net)**: `/api/auth/register` and `/api/auth/login` both have a per-IP sliding-window limiter. Too many wrong attempts from one IP locks it for a while (`429`); success resets the counter so legit users are unaffected. Thresholds are tunable via `REG_*` / `LOGIN_*` env vars (see `.env.example`).
   - Behind Zeabur's reverse proxy, the real client IP comes from `X-Forwarded-For`.
   - The counter is in-memory; fine for a single instance. If you scale to multiple replicas, switch to a shared store like Redis.

> Want it stricter? Make codes single-use (invalidated once consumed) or cap registrations per code — both can be done with a DB table in `app/services/users.py`. For personal use, a high-entropy code + rate limiting is usually enough.

## Daily targets & TDEE (computed per member)

Targets are no longer hardcoded — each member's **TDEE is estimated from their own body data** and converted into goals:

- **Auto estimate**: enter sex/age/height/weight/activity/goal → Mifflin-St Jeor BMR × activity factor = TDEE.
- **Body composition**: with a body fat % (from an InBody / smart scale), it switches to **Katch-McArdle** (lean-body-mass based, more accurate), and the protein target uses LBM too. If a scan reports a measured BMR, enter it to use directly (most accurate).
- **Manual**: if you already know your numbers, enter the calorie range and protein floor directly.

From TDEE and the goal (`cut`/`maintain`/`bulk`) it derives: a calorie target range, a protein target, and the **TDEE ceiling**.

| Formula | When |
|---|---|
| Mifflin-St Jeor | Only basic specs available |
| Katch-McArdle | Body fat % available (more accurate) |
| Measured BMR | A scan reports BMR directly (most accurate) |

Activity factors: sedentary 1.2 / light 1.375 / moderate 1.55 / active 1.725 / very active 1.9.
Goal adjustment: cut −400, maintain 0, bulk +250 kcal (override via `calorie_adjust`).

### The home-screen mascot

The calorie visual is a **round mascot** whose belly fills like a water level as you eat through the day:

- Below target → blue, half-empty.
- Inside the calorie target range → **turns green with a "goal met" glow**.
- Over target but still under TDEE → amber warning.
- **Over TDEE → it turns red, puffs up, overflows with drips over its head, face looks stuffed**, and shows "over TDEE by N kcal".

**Members without a profile**: no evaluation — the home screen just shows today's calories and prompts you to set up.
Protein below target still shows a clear home-screen alert (the key metric during a cut).
