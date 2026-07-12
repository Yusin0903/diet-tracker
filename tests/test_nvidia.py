"""NVIDIA vision prompt 組裝 + JSON 防呆解析的單元測試(不呼叫網路)。"""
import io

import pytest
from PIL import Image

from app.services.nvidia import ANALYZE_PROMPT, _extract_json, build_prompt, normalize_to_jpeg


def test_plain_prompt_unchanged():
    assert build_prompt() == ANALYZE_PROMPT
    assert build_prompt("") == ANALYZE_PROMPT
    assert build_prompt("   ") == ANALYZE_PROMPT


def test_hint_is_appended():
    p = build_prompt("油條")
    assert p.startswith(ANALYZE_PROMPT)
    assert "油條" in p
    assert "補充說明" in p


def test_prompt_has_no_copyable_example_values():
    # Regression: the old prompt's worked example ("雞胸便當", 431 kcal,
    # 38.0g protein) was a concrete, plausible-looking real answer, and the
    # (smaller, 11B) vision model kept parroting those exact numbers back
    # verbatim regardless of what was actually in the photo — a known
    # failure mode where a weaker instruction-following model treats a
    # worked example as "the answer" instead of a format template. The
    # prompt must use obvious placeholders and say not to copy them.
    assert "431" not in ANALYZE_PROMPT
    assert "38.0" not in ANALYZE_PROMPT
    assert "雞胸便當" not in ANALYZE_PROMPT
    assert "照抄" in ANALYZE_PROMPT


def test_extract_json_plain():
    assert _extract_json('{"name": "便當", "calories": 500}') == {"name": "便當", "calories": 500}


def test_extract_json_markdown_fence():
    text = '這是分析結果:\n```json\n{"name": "便當", "calories": 500}\n```'
    assert _extract_json(text) == {"name": "便當", "calories": 500}


def test_extract_json_stray_prose():
    # 開源模型有時會在 JSON 前後夾雜說明文字,不包 markdown 圍欄。
    text = 'Sure, here is the analysis: {"name": "便當", "calories": 500} Let me know if you need more.'
    assert _extract_json(text) == {"name": "便當", "calories": 500}


def test_extract_json_unparseable_raises():
    with pytest.raises(ValueError):
        _extract_json("我沒辦法分析這張照片。")


def _png_bytes(size=(400, 300), color=(200, 100, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


def _heic_bytes(size=(400, 300), color=(80, 160, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="HEIF", quality=80)
    return buf.getvalue()


def test_normalize_to_jpeg_plain_format():
    out = normalize_to_jpeg(_png_bytes())
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"


def test_normalize_to_jpeg_downscales_oversized_photos():
    out = normalize_to_jpeg(_png_bytes(size=(4000, 3000)), max_dim=1600)
    img = Image.open(io.BytesIO(out))
    assert max(img.size) <= 1600


def test_normalize_to_jpeg_handles_heic():
    # Regression test: Android Chrome generally can't decode HEIC/HEIF client
    # side (unlike iOS Safari), so the frontend's best-effort canvas
    # conversion falls back to the untouched original file on those devices —
    # this backend step is what must actually succeed regardless.
    out = normalize_to_jpeg(_heic_bytes())
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"


def test_normalize_to_jpeg_rejects_garbage():
    with pytest.raises(Exception):
        normalize_to_jpeg(b"not an image" * 50)
