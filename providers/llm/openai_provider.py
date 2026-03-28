"""OpenAI provider implementation for the pluggable LLM router."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from services.llm_provider import LLMResponse


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
            else:
                parts.append(str(part))
        return "\n".join(p for p in parts if p).strip()
    return str(content or "").strip()


def _extract_json_object(text: str) -> Dict[str, Any]:
    s = (text or "").strip()
    if not s:
        return {}
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", s)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


class OpenAIProvider:
    provider_name = "openai"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key

    def _build_llm(self, model: str, temperature: float, max_tokens: int) -> ChatOpenAI:
        kwargs: Dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        return ChatOpenAI(**kwargs)

    def generate_text(
        self,
        *,
        system_prompt: str,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        llm = self._build_llm(model, temperature, max_tokens)
        messages = []
        if system_prompt.strip():
            messages.append(SystemMessage(content=system_prompt.strip()))
        messages.append(HumanMessage(content=prompt.strip()))
        result = llm.invoke(messages)
        text = _content_to_text(getattr(result, "content", ""))
        return LLMResponse(text=text, provider=self.provider_name, model=model, raw={"content": text})

    def generate_json(
        self,
        *,
        system_prompt: str,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        llm = self._build_llm(model, temperature, max_tokens)
        messages = []
        if system_prompt.strip():
            messages.append(SystemMessage(content=system_prompt.strip()))
        messages.append(HumanMessage(content=prompt.strip()))
        result = llm.invoke(messages, response_format={"type": "json_object"})
        return _extract_json_object(_content_to_text(getattr(result, "content", "")))
