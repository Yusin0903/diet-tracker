"""Pydantic request models for the API."""
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class RegisterIn(BaseModel):
    username: str = Field(..., max_length=50)
    password: str = Field(..., max_length=128)  # Upper bound guards against huge-input hashing
    invite_code: str = Field(..., max_length=128)


class LoginIn(BaseModel):
    username: str = Field(..., max_length=50)
    password: str = Field(..., max_length=128)


class FriendRequestIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)


class SharePrefsIn(BaseModel):
    share_mascot: bool = True
    share_diet: bool = False
    share_recipes: bool = False


EX_TYPES = {"running", "strength", "yoga", "cycling", "swimming", "ball", "walking", "stretch", "other"}


class ExerciseIn(BaseModel):
    ex_type: str
    distance_km: Optional[float] = Field(None, ge=0, le=500)
    note: Optional[str] = Field(None, max_length=500)

    @field_validator("ex_type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        if v not in EX_TYPES:
            raise ValueError("運動類型不合法")
        return v


class MovementIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class SetIn(BaseModel):
    weight_kg: Optional[float] = Field(None, ge=0, le=1000)
    reps: int = Field(..., ge=1, le=1000)


class PlanIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    source_url: Optional[str] = Field(None, max_length=500)

    @field_validator("source_url")
    @classmethod
    def _http_only(cls, v: Optional[str]) -> Optional[str]:
        if v and v.strip() and not re.match(r"^https?://", v.strip(), re.IGNORECASE):
            raise ValueError("出處連結需為 http(s) 開頭")
        return v


class PlanMovementIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    target_sets: int = Field(3, ge=1, le=20)
    target_reps: int = Field(10, ge=1, le=100)


class EntryIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    calories: int = Field(..., ge=0, le=100_000)
    protein_g: float = Field(..., ge=0, le=10_000)
    source: str = Field("manual")  # 'photo' | 'manual' | 'favorite' | 'barcode' | 'recipe'
    note: Optional[str] = Field(None, max_length=500)


class EntryEdit(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    calories: int = Field(..., ge=0, le=100_000)
    protein_g: float = Field(..., ge=0, le=10_000)
    note: Optional[str] = Field(None, max_length=500)


class RecipeIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    servings: Optional[float] = Field(None, ge=0, le=10_000)
    calories: Optional[int] = Field(None, ge=0, le=100_000)      # Per serving
    protein_g: Optional[float] = Field(None, ge=0, le=10_000)    # Per serving
    ingredients: Optional[str] = Field(None, max_length=4000)
    steps: Optional[str] = Field(None, max_length=4000)
    video_url: Optional[str] = Field(None, max_length=500)

    @field_validator("video_url")
    @classmethod
    def _http_only(cls, v: Optional[str]) -> Optional[str]:
        # Reject javascript:/data: etc. — only allow real http(s) links.
        if v and v.strip() and not re.match(r"^https?://", v.strip(), re.IGNORECASE):
            raise ValueError("影片連結需為 http(s) 開頭")
        return v


class FoodIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    calories: int = Field(..., ge=0, le=100_000)
    protein_g: float = Field(..., ge=0, le=10_000)


class ProfileIn(BaseModel):
    mode: str = "auto"  # 'auto' | 'manual'
    # auto 輸入
    sex: Optional[str] = None
    age: Optional[int] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    body_fat_pct: Optional[float] = None
    measured_bmr: Optional[int] = None
    activity_level: Optional[str] = None
    goal: Optional[str] = None
    calorie_adjust: Optional[int] = None
    # manual 直接輸入目標
    calories_min: Optional[int] = None
    calories_max: Optional[int] = None
    protein_min: Optional[int] = None
