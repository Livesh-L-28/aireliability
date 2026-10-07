"""Python SDK asynchronous AsyncClient for the AI Reliability Platform (Phase 46)."""

from __future__ import annotations

from typing import Any

import httpx

from aireliability.api.app import api_app
from aireliability.sdk.client import (
    _map_http_error,
)


class AsyncEvaluationResource:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def create(
        self,
        input_text: str,
        output_text: str,
        trace_id: str | None = None,
        expected_output: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "input_text": input_text,
            "output_text": output_text,
            "trace_id": trace_id,
            "expected_output": expected_output,
        }
        if metadata is not None:
            payload["metadata"] = metadata
        return await self._client._request(
            "POST",
            "/api/v1/evaluations",
            json=payload,
        )

    async def get(self, evaluation_id: str) -> dict[str, Any]:
        return await self._client._request(
            "GET", f"/api/v1/evaluations/{evaluation_id}"
        )


class AsyncClient:
    """Asynchronous Python client for AI Reliability Platform."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str | None = None,
        timeout: float = 30.0,
        app: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or getattr(api_app.state, "dev_secret", None)
        self.timeout = timeout
        target_app = app if app is not None else api_app
        self._http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=target_app),
            base_url=self.base_url,
            timeout=timeout,
        )
        self.evaluations = AsyncEvaluationResource(self)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = kwargs.pop("headers", {})
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        resp = await self._http.request(method, path, headers=headers, **kwargs)
        if resp.status_code >= 400:
            try:
                err_detail = resp.json().get("detail", resp.text)
            except Exception:
                err_detail = resp.text
            raise _map_http_error(resp.status_code, str(err_detail))

        return resp.json()

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def get_health(self) -> dict[str, Any]:
        return await self.health()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()
