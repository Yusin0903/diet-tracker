"""飲控 App 後端入口。

FastAPI + Postgres + NVIDIA NIM vision,並 serve PWA 靜態檔。
路由按資源拆成各 APIRouter(app/routers/),這裡組裝起來。
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db import init_pool
from app.routers import (
    analyze, auth, entries, exercises, foods, friends, profile, recipes, stats, summary,
    workout_plans,
)
from app.settings import settings

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Content-Security-Policy: lock the page down to self + the few third parties we
# actually use (Google Fonts, the YouTube recipe embed, Open Food Facts lookups).
# Scripts are 'self' only — no inline scripts — which blunts XSS even though the
# auth token lives in localStorage. Inline style attributes are generated in JS,
# so styles need 'unsafe-inline'.
_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "script-src 'self'; "
    "connect-src 'self' https://world.openfoodfacts.org; "
    "frame-src https://www.youtube.com https://www.youtube-nocookie.com; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 啟動前先檢查關鍵密鑰已設定,避免帶著弱/空密鑰上線(token 可被偽造)。
    if not settings.secret_key:
        raise RuntimeError(
            "SECRET_KEY 尚未設定。請用 `openssl rand -hex 32` 產生一組,"
            "並以環境變數提供(正式環境務必設定且固定)。"
        )
    init_pool()
    yield


app = FastAPI(title="好好吃飯 App", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("Content-Security-Policy", _CSP)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    return resp


for module in (
    auth, analyze, entries, summary, foods, profile, recipes, stats, friends, exercises,
    workout_plans,
):
    app.include_router(module.router)


@app.get("/")
def index():
    # no-cache:每次都要跟伺服器確認是不是最新的,不然改版後使用者可能一直
    # 停在舊版(尤其 PWA 加到主畫面後,瀏覽器的 HTTP 快取比想像中頑固)。
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js")
def service_worker():
    # 同上,而且這支檔案本身決定了 PWA 要不要更新 —— 如果它被瀏覽器的 HTTP
    # 快取擋住、根本沒去問伺服器有沒有新版,sw.js 內建的版本比對機制
    # (skipWaiting / clients.claim)完全沒有機會執行,使用者就會卡在舊版。
    return FileResponse(
        FRONTEND_DIR / "sw.js", media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


# PWA 靜態檔(放最後,避免蓋掉 /api 路由)
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
