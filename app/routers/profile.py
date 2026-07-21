"""每位會員的每日目標:估算預覽 / 讀取 / 儲存。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import ProfileIn
from app.security import current_user
from app.services import targets
from app.services.profile import get_profile, save_profile

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("")
def read_profile(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    return {"profile": get_profile(user["id"], db)}


@router.post("/preview")
def preview_profile(body: ProfileIn, user: dict = Depends(current_user)):
    """只估算、不存檔,讓前端在儲存前先看 TDEE 與目標。"""
    try:
        return targets.compute(body.model_dump())
    except targets.TargetError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("")
def update_profile(
    body: ProfileIn, user: dict = Depends(current_user), db: Session = Depends(get_db)
):
    data = body.model_dump()
    try:
        result = targets.compute(data)
    except targets.TargetError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_profile(user["id"], data, result, db)
    return {"saved": True, "result": result, "profile": get_profile(user["id"], db)}
