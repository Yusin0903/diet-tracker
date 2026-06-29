"""飲控 App 後端入口。

FastAPI + Postgres + Gemini vision,並 serve PWA 靜態檔。
路由按資源拆成各 APIRouter(app/routers/),這裡組裝起來。
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db import init_pool
from app.routers import analyze, auth, entries, foods, profile, recipes, stats, summary
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


for module in (auth, analyze, entries, summary, foods, profile, recipes, stats):
    app.include_router(module.router)


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


# PWA 靜態檔(放最後,避免蓋掉 /api 路由)
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
