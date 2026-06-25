"""Gemini 圖片分析:只回估值,不寫 DB(等使用者確認後才呼叫 /api/entries)。"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.security import current_user
from app.services.gemini import analyze_food_image

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze")
async def analyze(file: UploadFile = File(...), user: dict = Depends(current_user)):
    image_bytes = await file.read()
    try:
        result = analyze_food_image(image_bytes, file.content_type or "image/jpeg")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"分析失敗,請改用手動輸入:{e}")
    return result
