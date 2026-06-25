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

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
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
