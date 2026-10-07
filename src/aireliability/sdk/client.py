"""Python SDK synchronous Client for the AI Reliability Platform (Phase 46)."""

from __future__ import annotations

import contextlib
from typing import Any

import httpx

from aireliability.api.app import api_app


class APIError(Exception):
    """Base exception for SDK errors."""

    def __init__(
        self, message: str, status_code: int = 500, details: Any = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class AuthenticationError(APIError):
    pass


class AuthorizationError(APIError):
    pass


class ValidationError(APIError):
    pass


class RateLimitError(APIError):
    pass


class NotFoundError(APIError):
    pass


class ConflictError(APIError):
    pass


class PolicyBlockedError(APIError):
    pass


class TenantIsolationError(APIError):
    pass


class ServerError(APIError):
    pass


def _map_http_error(status_code: int, detail: str) -> APIError:
    """Map HTTP status codes to typed SDK exceptions."""
    if status_code == 401:
        return AuthenticationError(detail, status_code=status_code)
    elif status_code == 403:
        if "tenant" in detail.lower():
            return TenantIsolationError(detail, status_code=status_code)
        elif "policy" in detail.lower():
            return PolicyBlockedError(detail, status_code=status_code)
        return AuthorizationError(detail, status_code=status_code)
    elif status_code == 404:
        return NotFoundError(detail, status_code=status_code)
    elif status_code == 409:
        return ConflictError(detail, status_code=status_code)
    elif status_code == 422:
        return ValidationError(detail, status_code=status_code)
    elif status_code == 429:
        return RateLimitError(detail, status_code=status_code)
    return ServerError(detail, status_code=status_code)


class _ResourceBase:
    def __init__(self, client: Client) -> None:
        self._client = client


class EvaluationResource(_ResourceBase):
    def create(
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
        return self._client._request(
            "POST",
            "/api/v1/evaluations",
            json=payload,
        )

    def get(self, evaluation_id: str) -> dict[str, Any]:
        return self._client._request("GET", f"/api/v1/evaluations/{evaluation_id}")


class DatasetResource(_ResourceBase):
    def create(
        self, name: str, items: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        return self._client._request(
            "POST", "/api/v1/datasets", json={"name": name, "items": items or []}
        )

    def list(self) -> list[dict[str, Any]]:
        return self._client._request("GET", "/api/v1/datasets")


class SafetyResource(_ResourceBase):
    def evaluate(self, target_id: str = "target_llm") -> dict[str, Any]:
        return self._client._request(
            "POST", "/api/v1/safety/evaluate", json={"target_id": target_id}
        )

    def run_campaign(
        self, target_id: str = "target_system", max_tests: int = 10
    ) -> dict[str, Any]:
        return self._client._request(
            "POST",
            "/api/v1/safety/campaign",
            json={"target_id": target_id, "max_tests": max_tests},
        )


class PredictionResource(_ResourceBase):
    def predict(self, target_id: str = "pipeline_1") -> dict[str, Any]:
        return self._client._request(
            "POST", "/api/v1/predictions", json={"target_id": target_id}
        )


class DashboardResource(_ResourceBase):
    def get(self) -> dict[str, Any]:
        return self._client._request("GET", "/api/v1/dashboard")

    def get_health(self) -> dict[str, Any]:
        return self._client._request("GET", "/api/v1/dashboard/health")


class PolicyResource(_ResourceBase):
    def evaluate(self, context: dict[str, Any]) -> dict[str, Any]:
        return self._client._request("POST", "/api/v1/policies/evaluate", json=context)


class TenantResource(_ResourceBase):
    def list(self) -> list[dict[str, Any]]:
        return self._client._request("GET", "/api/v1/tenants")

    def create(self, name: str, tenant_id: str | None = None) -> dict[str, Any]:
        return self._client._request(
            "POST", "/api/v1/tenants", json={"name": name, "tenant_id": tenant_id}
        )


class Client:
    """Synchronous Python client for AI Reliability Platform."""

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
        if app is not None:
            from fastapi.testclient import TestClient

            self._http: Any = TestClient(app, base_url=self.base_url)
        else:
            self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

        self.evaluations = EvaluationResource(self)
        self.datasets = DatasetResource(self)
        self.safety = SafetyResource(self)
        self.predictions = PredictionResource(self)
        self.dashboard = DashboardResource(self)
        self.policies = PolicyResource(self)
        self.tenants = TenantResource(self)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = kwargs.pop("headers", {})
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        resp = self._http.request(method, path, headers=headers, **kwargs)
        if resp.status_code >= 400:
            try:
                err_detail = resp.json().get("detail", resp.text)
            except Exception:
                err_detail = resp.text
            raise _map_http_error(resp.status_code, str(err_detail))

        return resp.json()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def get_health(self) -> dict[str, Any]:
        return self.health()

    def close(self) -> None:
        if hasattr(self._http, "close"):
            with contextlib.suppress(Exception):
                self._http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
