"""API 的 Pydantic 請求模型。"""
from typing import Optional

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    username: str
    password: str
    invite_code: str


class LoginIn(BaseModel):
    username: str
    password: str


class EntryIn(BaseModel):
    name: str = Field(..., min_length=1)
    calories: int = Field(..., ge=0)
    protein_g: float = Field(..., ge=0)
    source: str = Field("manual")  # 'photo' | 'manual' | 'favorite' | 'barcode' | 'recipe'
    note: Optional[str] = None


class EntryEdit(BaseModel):
    name: str = Field(..., min_length=1)
    calories: int = Field(..., ge=0)
    protein_g: float = Field(..., ge=0)
    note: Optional[str] = None


class RecipeIn(BaseModel):
    name: str = Field(..., min_length=1)
    servings: Optional[float] = Field(None, ge=0)
    calories: Optional[int] = Field(None, ge=0)      # 每份熱量
    protein_g: Optional[float] = Field(None, ge=0)   # 每份蛋白
    ingredients: Optional[str] = None
    steps: Optional[str] = None


class FoodIn(BaseModel):
    name: str = Field(..., min_length=1)
    calories: int = Field(..., ge=0)
    protein_g: float = Field(..., ge=0)


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
