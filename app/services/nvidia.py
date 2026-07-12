"""NVIDIA NIM vision 整合(build.nvidia.com,OpenAI 相容 API,免費方案)。

跟 Gemini 不同,開源視覺模型的 JSON 模式不保證乾淨,所以除了在 prompt 裡強制
「只回 JSON」,還多一層防呆:先直接 parse,失敗再從回應文字挖出
```json ... ``` 或第一個 {...} 區塊。API key 只在後端。

圖片一律在後端用 Pillow 重新編碼成 JPEG 再送給模型 —— 前端雖然也會盡量轉檔,
但那只是「盡力而為」:Android 上的 Chrome 大多不支援解 HEIC/HEIF(不像
iOS Safari 有內建系統級解碼器),前端轉檔在這類裝置上必然失敗、只能退回原始
檔案,而視覺模型的解碼器一樣吃不下 HEIC/HEIF,結果又是同一個「cannot
identify image file」錯誤。後端這一步用 pillow-heif 掛的 HEIF/HEIC 解碼器
不依賴瀏覽器能力,才是真正保底、不管來源裝置/瀏覽器是什麼都能處理的地方。
"""
import base64
import io
import json
import re

import pillow_heif
from openai import OpenAI
from PIL import Image

from app.settings import settings

pillow_heif.register_heif_opener()  # 讓 PIL.Image.open() 認得 .heic / .heif

_MAX_DIM = 1600  # 長邊上限,跟前端轉檔的設定一致

ANALYZE_PROMPT = """你是營養估算助手。分析這張食物照片,估算整份餐點的熱量與蛋白質。
規則:
- 只回傳 JSON,不要任何其他文字、不要 markdown 的 ``` 包裹。
- 熱量單位 kcal(整數),蛋白質單位克(可帶一位小數)。
- 看不出油量/醬料時,估一個合理的中間值,寧可略保守。
- name 用簡短中文描述整份餐點。
- 下面只是示範 JSON 的「格式」,< > 裡的內容都是佔位符,不是真實數字或食物,
  跟這張照片完全無關。你必須依照片實際看到的東西自己判斷、自己計算,
  絕對不能照抄下面任何一個數字或名稱。
格式(< > 換成你自己算出來的值,輸出時不要留 < >):
{
  "name": "<這張照片裡的食物,簡短中文描述>",
  "calories": <你估算的整數 kcal>,
  "protein_g": <你估算的蛋白質克數,可一位小數>,
  "items": [
    {"food": "<辨識出的食材>", "calories": <整數>, "protein_g": <數字>}
  ],
  "confidence": "<high 或 medium 或 low>"
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


def normalize_to_jpeg(image_bytes: bytes, max_dim: int = _MAX_DIM, quality: int = 85) -> bytes:
    """不管來源格式/裝置為何,一律解碼後重新編碼成 JPEG(順便縮到長邊上限)。"""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def analyze_food_image(image_bytes: bytes, hint: str | None = None) -> dict:
    client = _get_client()
    jpeg_bytes = normalize_to_jpeg(image_bytes)
    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    resp = client.chat.completions.create(
        model=settings.nvidia_model,
        temperature=0.2,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": build_prompt(hint)},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
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
