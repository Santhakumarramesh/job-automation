from __future__ import annotations

import pytest

from services.llm_provider import LLMResponse


def test_resolve_provider_auto_prefers_anthropic(monkeypatch: pytest.MonkeyPatch):
    from services import model_router as mr

    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    assert mr.resolve_provider() == "anthropic"


def test_generate_json_required_keys_fallback(monkeypatch: pytest.MonkeyPatch):
    from services import model_router as mr

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")

    providers_called: list[str] = []

    def _fake_call_json(*, provider_name: str, model: str, system_prompt: str, prompt: str, temperature: float, max_tokens: int):
        providers_called.append(provider_name)
        if len(providers_called) == 1:
            return {"answer": "No fabrication."}
        return {
            "answer": "No fabrication.",
            "manual_review_required": True,
            "reason_codes": ["generic_llm_answer"],
        }

    monkeypatch.setattr(mr, "_call_json", _fake_call_json)

    out = mr.generate_json(
        prompt="return structured answer",
        required_keys=("answer", "manual_review_required", "reason_codes"),
    )

    assert out["status"] == "ok"
    assert out.get("fallback") is True
    assert providers_called == ["openai", "anthropic"]


def test_generate_text_provider_fallback(monkeypatch: pytest.MonkeyPatch):
    from services import model_router as mr

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")

    def _fake_call_text(*, provider_name: str, model: str, system_prompt: str, prompt: str, temperature: float, max_tokens: int):
        if provider_name == "openai":
            raise RuntimeError("openai_down")
        return LLMResponse(text="ok", provider=provider_name, model=model, raw={})

    monkeypatch.setattr(mr, "_call_text", _fake_call_text)

    out = mr.generate_text(prompt="hello")
    assert out["status"] == "ok"
    assert out.get("fallback") is True
    assert out["provider"] == "anthropic"
