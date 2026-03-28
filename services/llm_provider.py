"""Shared LLM provider interfaces and response types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    raw: Optional[Dict[str, Any]] = None


class LLMProvider(Protocol):
    provider_name: str

    def generate_text(
        self,
        *,
        system_prompt: str,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        ...

    def generate_json(
        self,
        *,
        system_prompt: str,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        ...
