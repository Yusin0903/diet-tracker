"""Gemini 2.5 Flash vision 整合。

關鍵:prompt 強制只回 JSON + response_mime_type=application/json,
後端 parse 完直接用。API key 只在後端。
"""
import json

from google import genai
from google.genai import types

import config

ANALYZE_PROMPT = """你是營養估算助手。分析這張食物照片,估算整份餐點的熱量與蛋白質。
規則:
- 只回傳 JSON,不要任何其他文字、不要 markdown 的 ``` 包裹。
- 熱量單位 kcal(整數),蛋白質單位克(可帶一位小數)。
- 看不出油量/醬料時,估一個合理的中間值,寧可略保守。
- name 用簡短中文描述整份餐點。
回傳格式:
{
  "name": "雞胸便當",
  "calories": 431,
  "protein_g": 38.0,
  "items": [
    {"food": "雞胸肉", "calories": 180, "protein_g": 30},
    {"food": "白飯", "calories": 200, "protein_g": 4}
  ],
  "confidence": "high"
}"""

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY 尚未設定")
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def analyze_food_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    client = _get_client()
    resp = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ANALYZE_PROMPT,
        ],
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",  # 強制乾淨 JSON 輸出
        ),
    )
    data = json.loads(resp.text)
    # 防呆:確保欄位齊全
    return {
        "name": data.get("name", "未知食物"),
        "calories": int(data.get("calories", 0)),
        "protein_g": float(data.get("protein_g", 0)),
        "items": data.get("items", []),
        "confidence": data.get("confidence", "low"),
    }
