"""Thin Ollama client. Local, free, and easy to fake in tests."""
from __future__ import annotations

import json
from typing import Protocol

import httpx

from .config import settings


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    def chat_json(self, system: str, user: str) -> dict: ...


class OllamaClient:
    def __init__(self, host: str | None = None, model: str | None = None, timeout: float = 180.0):
        self.host = (host or settings.ollama_host).rstrip("/")
        self.model = model or settings.model
        self.timeout = timeout

    def chat_json(self, system: str, user: str) -> dict:
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.3},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            r = httpx.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
            r.raise_for_status()
            content = r.json()["message"]["content"]
            data = json.loads(content)
        except (httpx.HTTPError, KeyError, json.JSONDecodeError) as e:
            raise LLMError(f"{type(e).__name__}: {e}") from e
        if not isinstance(data, dict):
            raise LLMError("model did not return a JSON object")
        return data

    def health(self) -> tuple[bool, str]:
        """Return (ok, message) for the `doctor` command."""
        try:
            r = httpx.get(f"{self.host}/api/tags", timeout=5)
            r.raise_for_status()
        except httpx.HTTPError as e:
            return False, f"Ollama not reachable at {self.host} ({type(e).__name__}). Start it with: ollama serve"
        names = [m.get("name", "") for m in r.json().get("models", [])]
        wanted = {self.model, f"{self.model}:latest"}
        if not wanted & set(names):
            return False, f"Model '{self.model}' not pulled. Run: ollama pull {self.model}  (installed: {', '.join(names) or 'none'})"
        return True, f"Ollama OK, model '{self.model}' available"
