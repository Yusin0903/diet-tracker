"""Vision image analysis (NVIDIA NIM): returns an estimate only, never writes
to the DB (the user confirms first, then /api/entries persists it)."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.rate_limit import UsageLimiter
from app.security import current_user
from app.services.nvidia import analyze_food_image
from app.settings import settings

router = APIRouter(prefix="/api", tags=["analyze"])
logger = logging.getLogger("diet.analyze")

# Throttle this endpoint per user, and cap upload size.
_analyze_limiter = UsageLimiter(settings.analyze_max_per_window, settings.analyze_window_s)
_MAX_BYTES = settings.max_upload_mb * 1024 * 1024


@router.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    hint: Optional[str] = Form(None),  # Optional free-text hint from the user
    user: dict = Depends(current_user),
):
    _analyze_limiter.hit(f"analyze:{user['id']}")  # Per-user rate cap (429 if exceeded)
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="只接受圖片檔")
    # Bounded read: never pull more than the cap into memory.
    image_bytes = await file.read(_MAX_BYTES + 1)
    if len(image_bytes) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"圖片太大,上限 {settings.max_upload_mb}MB")
    if not image_bytes:
        raise HTTPException(status_code=400, detail="沒有讀到圖片內容")
    try:
        result = analyze_food_image(image_bytes, hint)
    except Exception:  # noqa: BLE001
        # Log the detail server-side, return a generic message (don't leak internals).
        logger.exception("Vision analyze failed")
        raise HTTPException(status_code=502, detail="分析失敗,請改用手動輸入")
    return result
