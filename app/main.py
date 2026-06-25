"""飲控 App 後端入口。

FastAPI + Postgres + Gemini vision,並 serve PWA 靜態檔。
路由按資源拆成各 APIRouter(app/routers/),這裡組裝起來。
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db import init_pool
from app.routers import analyze, auth, entries, foods, profile, summary
from app.settings import settings

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


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


app = FastAPI(title="飲控 App", lifespan=lifespan)

for module in (auth, analyze, entries, summary, foods, profile):
    app.include_router(module.router)


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


# PWA 靜態檔(放最後,避免蓋掉 /api 路由)
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
