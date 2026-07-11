"""NVIDIA vision prompt 組裝 + JSON 防呆解析的單元測試(不呼叫網路)。"""
import pytest

from app.services.nvidia import ANALYZE_PROMPT, _extract_json, build_prompt


def test_plain_prompt_unchanged():
    assert build_prompt() == ANALYZE_PROMPT
    assert build_prompt("") == ANALYZE_PROMPT
    assert build_prompt("   ") == ANALYZE_PROMPT


def test_hint_is_appended():
    p = build_prompt("油條")
    assert p.startswith(ANALYZE_PROMPT)
    assert "油條" in p
    assert "補充說明" in p


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
