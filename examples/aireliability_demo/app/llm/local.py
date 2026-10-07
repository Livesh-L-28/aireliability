"""Optional local LLM provider (Ollama / Local HTTP) with automatic deterministic fallback."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from aireliability_demo.app.llm.deterministic import DeterministicLLM
from aireliability_demo.app.llm.interface import LLMProvider

logger = logging.getLogger(__name__)


class OptionalLocalLLM(LLMProvider):
    """Local LLM adapter connecting to local Ollama/HTTP inference if available.

    Falls back transparently to DeterministicLLM if the local server is not running,
    ensuring 100% offline, reproducible execution in all environments.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        timeout: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._fallback = DeterministicLLM()
        self._is_available: bool | None = None

    def is_available(self) -> bool:
        """Check if local Ollama/HTTP inference endpoint is reachable."""
        if self._is_available is not None:
            return self._is_available

        try:
            with httpx.Client(timeout=1.0) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                self._is_available = resp.status_code == 200
        except Exception:
            self._is_available = False

        return self._is_available

    def generate(self, prompt: str, scenario: str = "NORMAL", **kwargs: Any) -> str:
        """Generate response via local LLM if online, else use DeterministicLLM."""
        if scenario.upper() != "NORMAL" or not self.is_available():
            return self._fallback.generate(prompt, scenario=scenario, **kwargs)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                }
                resp = client.post(f"{self.base_url}/api/generate", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return str(data.get("response", ""))
        except Exception as exc:
            logger.warning(
                "Local LLM call failed (%s); falling back to DeterministicLLM", exc
            )

        return self._fallback.generate(prompt, scenario=scenario, **kwargs)

    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        scenario: str = "NORMAL",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate structured response, delegating to deterministic fallback if offline."""
        if scenario.upper() != "NORMAL" or not self.is_available():
            return self._fallback.generate_structured(
                prompt, schema=schema, scenario=scenario, **kwargs
            )

        raw = self.generate(prompt, scenario=scenario, **kwargs)
        return {
            "answer": raw,
            "provider": f"ollama:{self.model}",
            "status": "success",
        }
