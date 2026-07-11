"""NVIDIA NIM vision 整合(build.nvidia.com,OpenAI 相容 API,免費方案)。

跟 Gemini 不同,開源視覺模型的 JSON 模式不保證乾淨,所以除了在 prompt 裡強制
「只回 JSON」,還多一層防呆:先直接 parse,失敗再從回應文字挖出
```json ... ``` 或第一個 {...} 區塊。API key 只在後端。
"""
import base64
import json
import re

from openai import OpenAI

from app.settings import settings

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

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.nvidia_api_key:
            raise RuntimeError("NVIDIA_API_KEY 尚未設定")
        _client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=settings.nvidia_api_key)
    return _client


def build_prompt(hint: str | None = None) -> str:
    """組 prompt;使用者有給文字補充時併入,提高辨識準確度。"""
    prompt = ANALYZE_PROMPT
    if hint and hint.strip():
        prompt += (
            "\n\n使用者補充說明(很重要,請優先據此判斷食物種類,不要自行改成相似的東西):"
            f"\n{hint.strip()}"
        )
    return prompt


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        return json.loads(brace.group(0))
    raise ValueError("模型沒有回傳可解析的 JSON")


def analyze_food_image(
    image_bytes: bytes, mime_type: str = "image/jpeg", hint: str | None = None
) -> dict:
    client = _get_client()
    b64 = base64.b64encode(image_bytes).decode("ascii")
    resp = client.chat.completions.create(
        model=settings.nvidia_model,
        temperature=0.2,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": build_prompt(hint)},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                ],
            }
        ],
    )
    data = _extract_json(resp.choices[0].message.content)
    # 防呆:確保欄位齊全
    return {
        "name": data.get("name", "未知食物"),
        "calories": int(data.get("calories", 0)),
        "protein_g": float(data.get("protein_g", 0)),
        "items": data.get("items", []),
        "confidence": data.get("confidence", "low"),
    }
