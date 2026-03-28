"""Anthropic provider implementation for the pluggable LLM router."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from services.llm_provider import LLMResponse


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


class AnthropicProvider:
    provider_name = "anthropic"

    def __init__(self, api_key: Optional[str] = None, timeout_seconds: int = 60) -> None:
        self.api_key = (api_key or "").strip()
        self.timeout_seconds = max(10, int(timeout_seconds))

    def _post_messages(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                parsed = json.loads(body)
                return parsed if isinstance(parsed, dict) else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
            raise RuntimeError(f"Anthropic HTTP {e.code}: {body[:300]}") from e
        except Exception as e:
            raise RuntimeError(str(e)) from e

    def _extract_text(self, payload: Dict[str, Any]) -> str:
        content = payload.get("content")
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "\n".join(p for p in parts if p).strip()

    def generate_text(
        self,
        *,
        system_prompt: str,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        payload: Dict[str, Any] = {
            "model": model,
            "max_tokens": max(128, int(max_tokens)),
            "temperature": float(temperature),
            "messages": [{"role": "user", "content": prompt.strip()}],
        }
        if system_prompt.strip():
            payload["system"] = system_prompt.strip()

        raw = self._post_messages(payload)
        text = self._extract_text(raw)
        return LLMResponse(text=text, provider=self.provider_name, model=model, raw=raw)

    def generate_json(
        self,
        *,
        system_prompt: str,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        json_prompt = (
            f"{prompt.strip()}\n\n"
            "Return only a valid JSON object. Do not add commentary or markdown fences."
        )
        response = self.generate_text(
            system_prompt=system_prompt,
            prompt=json_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return _extract_json_object(response.text)
