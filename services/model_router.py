"""Model router for pluggable reasoning/writing providers."""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, Optional

from providers.llm import AnthropicProvider, OpenAIProvider
from services.llm_provider import LLMProvider, LLMResponse


_DEFAULT_MODELS = {
    "openai": {
        "fast": "gpt-4o-mini",
        "reasoning": "gpt-4o",
    },
    "anthropic": {
        "fast": "claude-3-5-haiku-latest",
        "reasoning": "claude-sonnet-4-5",
    },
}


def _clean_provider_name(name: Optional[str]) -> str:
    p = (name or "").strip().lower()
    if p in {"openai", "anthropic"}:
        return p
    return "auto"


def resolve_provider(provider: Optional[str] = None) -> str:
    p = _clean_provider_name(provider)
    if p != "auto":
        return p

    env_provider = _clean_provider_name(os.getenv("LLM_PROVIDER", "auto"))
    if env_provider != "auto":
        return env_provider

    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        return "anthropic"
    return "openai"


def _provider_has_key(name: str) -> bool:
    if name == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def _make_provider(name: str) -> LLMProvider:
    if name == "anthropic":
        return AnthropicProvider(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    return OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY", ""))


def resolve_model(
    *,
    provider: str,
    task: str = "reasoning",
    explicit_model: str = "",
) -> str:
    if explicit_model.strip():
        return explicit_model.strip()

    task_key = "fast" if str(task or "").strip().lower() == "fast" else "reasoning"

    env_model = os.getenv("LLM_MODEL_FAST" if task_key == "fast" else "LLM_MODEL_REASONING", "").strip()
    if env_model:
        return env_model

    return _DEFAULT_MODELS.get(provider, _DEFAULT_MODELS["openai"])[task_key]


def _validate_required_keys(data: Dict[str, Any], required_keys: Iterable[str]) -> Optional[str]:
    missing = [k for k in required_keys if k not in data]
    if missing:
        return f"missing_keys:{','.join(missing)}"
    return None


def _call_text(
    *,
    provider_name: str,
    model: str,
    system_prompt: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
) -> LLMResponse:
    provider = _make_provider(provider_name)
    return provider.generate_text(
        system_prompt=system_prompt,
        prompt=prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _call_json(
    *,
    provider_name: str,
    model: str,
    system_prompt: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
) -> Dict[str, Any]:
    provider = _make_provider(provider_name)
    return provider.generate_json(
        system_prompt=system_prompt,
        prompt=prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def generate_text(
    *,
    prompt: str,
    system_prompt: str = "",
    provider: Optional[str] = None,
    model: str = "",
    task: str = "reasoning",
    temperature: float = 0.2,
    max_tokens: int = 900,
    allow_fallback: bool = True,
) -> Dict[str, Any]:
    selected_provider = resolve_provider(provider)
    selected_model = resolve_model(provider=selected_provider, task=task, explicit_model=model)

    try:
        resp = _call_text(
            provider_name=selected_provider,
            model=selected_model,
            system_prompt=system_prompt,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return {
            "status": "ok",
            "text": resp.text,
            "provider": resp.provider,
            "model": resp.model,
        }
    except Exception as e:
        first_error = str(e)[:300]

    if not allow_fallback:
        return {
            "status": "error",
            "message": first_error,
            "provider": selected_provider,
            "model": selected_model,
        }

    fallback_provider = "openai" if selected_provider == "anthropic" else "anthropic"
    if not _provider_has_key(fallback_provider):
        fallback_provider = selected_provider

    fallback_model = os.getenv("LLM_MODEL_FALLBACK", "").strip() or resolve_model(
        provider=fallback_provider,
        task="fast",
    )

    try:
        resp = _call_text(
            provider_name=fallback_provider,
            model=fallback_model,
            system_prompt=system_prompt,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return {
            "status": "ok",
            "text": resp.text,
            "provider": resp.provider,
            "model": resp.model,
            "fallback": True,
            "fallback_from": selected_provider,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"{first_error} | fallback_failed:{str(e)[:220]}",
            "provider": selected_provider,
            "model": selected_model,
        }


def generate_json(
    *,
    prompt: str,
    system_prompt: str = "",
    provider: Optional[str] = None,
    model: str = "",
    task: str = "reasoning",
    temperature: float = 0.0,
    max_tokens: int = 900,
    required_keys: Optional[Iterable[str]] = None,
    allow_fallback: bool = True,
) -> Dict[str, Any]:
    selected_provider = resolve_provider(provider)
    selected_model = resolve_model(provider=selected_provider, task=task, explicit_model=model)

    try:
        data = _call_json(
            provider_name=selected_provider,
            model=selected_model,
            system_prompt=system_prompt,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if not isinstance(data, dict):
            raise ValueError("non_object_json")
        if required_keys:
            err = _validate_required_keys(data, required_keys)
            if err:
                raise ValueError(err)
        return {
            "status": "ok",
            "data": data,
            "provider": selected_provider,
            "model": selected_model,
        }
    except Exception as e:
        first_error = str(e)[:300]

    if not allow_fallback:
        return {
            "status": "error",
            "message": first_error,
            "provider": selected_provider,
            "model": selected_model,
            "data": {},
        }

    fallback_provider = "openai" if selected_provider == "anthropic" else "anthropic"
    if not _provider_has_key(fallback_provider):
        fallback_provider = selected_provider

    fallback_model = os.getenv("LLM_MODEL_FALLBACK", "").strip() or resolve_model(
        provider=fallback_provider,
        task="fast",
    )

    try:
        data = _call_json(
            provider_name=fallback_provider,
            model=fallback_model,
            system_prompt=system_prompt,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if not isinstance(data, dict):
            raise ValueError("non_object_json")
        if required_keys:
            err = _validate_required_keys(data, required_keys)
            if err:
                raise ValueError(err)
        return {
            "status": "ok",
            "data": data,
            "provider": fallback_provider,
            "model": fallback_model,
            "fallback": True,
            "fallback_from": selected_provider,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"{first_error} | fallback_failed:{str(e)[:220]}",
            "provider": selected_provider,
            "model": selected_model,
            "data": {},
        }


def answer_question(
    *,
    question_text: str,
    profile_json: str,
    resume_excerpt: str,
    job_context_json: str = "",
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    system_prompt = (
        "You are a truthful application assistant. Use only supplied candidate facts. "
        "If unsupported, mark manual_review_required true."
    )
    prompt = f"""Return JSON with keys: answer, manual_review_required, reason_codes.

Question: {question_text}
Profile: {profile_json}
Resume excerpt: {resume_excerpt}
Job context: {job_context_json}

Constraints:
- No fabrication.
- Keep answer concise (<=150 chars if possible).
- reason_codes is a JSON array of stable snake_case strings.
"""
    return generate_json(
        prompt=prompt,
        system_prompt=system_prompt,
        provider=provider,
        task="reasoning",
        required_keys=("answer", "manual_review_required", "reason_codes"),
    )


def rewrite_resume_bullet(
    *,
    bullet_text: str,
    job_description: str,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    system_prompt = "Rewrite for clarity and impact without adding unsupported claims."
    prompt = f"""Rewrite this resume bullet to align with the job while preserving facts.

Bullet: {bullet_text}
Job description: {job_description[:1200]}

Return only rewritten bullet text.
"""
    return generate_text(
        prompt=prompt,
        system_prompt=system_prompt,
        provider=provider,
        task="reasoning",
        temperature=0.2,
        max_tokens=220,
    )


def summarize_fit(
    *,
    fit_json: str,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    system_prompt = "Summarize fit assessments clearly and conservatively."
    prompt = f"""Summarize this fit result in 3 short bullets.

Fit data: {fit_json}

Return plain text only.
"""
    return generate_text(
        prompt=prompt,
        system_prompt=system_prompt,
        provider=provider,
        task="fast",
        temperature=0.1,
        max_tokens=220,
    )
