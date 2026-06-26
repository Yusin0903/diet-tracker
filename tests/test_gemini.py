"""gemini prompt 組裝的單元測試(不呼叫網路)。"""
from app.services.gemini import ANALYZE_PROMPT, build_prompt


def test_plain_prompt_unchanged():
    assert build_prompt() == ANALYZE_PROMPT
    assert build_prompt("") == ANALYZE_PROMPT
    assert build_prompt("   ") == ANALYZE_PROMPT


def test_hint_is_appended():
    p = build_prompt("油條")
    assert p.startswith(ANALYZE_PROMPT)
    assert "油條" in p
    assert "補充說明" in p
