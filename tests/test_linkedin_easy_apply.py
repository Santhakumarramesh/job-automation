"""LinkedIn Easy Apply selector list (centralized for MCP / runner)."""

from services.linkedin_easy_apply import LINKEDIN_EASY_APPLY_BUTTON_SELECTORS


def test_easy_apply_selector_list_nonempty():
    assert len(LINKEDIN_EASY_APPLY_BUTTON_SELECTORS) >= 6
    assert any("Easy Apply" in s or "easy apply" in s.lower() for s in LINKEDIN_EASY_APPLY_BUTTON_SELECTORS)
