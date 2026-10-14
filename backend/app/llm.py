"""Pluggable LLM clients. `get_client` returns None when no model is configured; callers then use templates."""
from __future__ import annotations

from typing import Protocol

import httpx

from .config import Settings, get_settings


class LLMError(Exception):
    pass


class Client(Protocol):
    def complete(self, system: str, user: str, json_mode: bool = False) -> str: ...


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 300):
        self.base_url, self.model, self.timeout = base_url.rstrip("/"), model, timeout

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        body = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            # repeat_penalty and num_predict avoid the 3B "token repeat limit reached" HTTP 500
            "options": {"temperature": 0.4, "repeat_penalty": 1.15, "num_predict": 400},
        }
        if json_mode:
            body["format"] = "json"
        try:
            r = httpx.post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise LLMError(f"ollama unreachable: {exc}") from exc
        if r.status_code != 200:
            raise LLMError(f"ollama HTTP {r.status_code}: {r.text[:300]}")
        return r.json()["message"]["content"].strip()


class OpenAIClient:
    """Any OpenAI-compatible /v1/chat/completions server."""

    def __init__(self, base_url: str, model: str, api_key: str, timeout: float = 120):
        self.base_url, self.model, self.api_key, self.timeout = base_url.rstrip("/"), model, api_key, timeout

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        body = {
            "model": self.model,
            "temperature": 0.4,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            r = httpx.post(
                f"{self.base_url}/v1/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"llm unreachable: {exc}") from exc
        if r.status_code != 200:
            raise LLMError(f"llm HTTP {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"].strip()


def get_client(settings: Settings | None = None) -> Client | None:
    s = settings or get_settings()
    if s.llm_provider == "ollama":
        return OllamaClient(s.llm_base_url, s.llm_model)
    if s.llm_provider == "openai":
        return OpenAIClient(s.llm_base_url, s.llm_model, s.llm_api_key)
    return None
