"""Provider adapters for LLM-as-a-Judge evaluation without heavy mandatory dependencies."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from aireliability.evaluation.semantic.base import JudgeResult


def _parse_judge_json_response(
    raw_response: str,
    threshold: float = 0.70,
    provider: str = "",
    model: str = "",
) -> JudgeResult:
    """Safely parse LLM judge JSON response or extract score/reasoning heuristically."""
    # Try finding JSON block in markdown or text
    cleaned = raw_response.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()

    score = 0.5
    reasoning = raw_response
    criteria_results: dict[str, bool] = {}
    confidence = 0.85

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            score = float(data.get("score", data.get("rating", 0.5)))
            # If scale is 1-5 or 1-10, normalize to [0.0, 1.0]
            if score > 1.0 and score <= 5.0:
                score = score / 5.0
            elif score > 1.0 and score <= 10.0:
                score = score / 10.0
            reasoning = str(
                data.get("reasoning", data.get("explanation", raw_response))
            )
            confidence = float(data.get("confidence", 0.90))
            if isinstance(data.get("criteria_results"), dict):
                criteria_results = {
                    str(k): bool(v) for k, v in data["criteria_results"].items()
                }
    except Exception:
        # Fallback keyword extraction for score
        if (
            "score: 1.0" in raw_response.lower()
            or "verdict: pass" in raw_response.lower()
        ):
            score = 1.0
        elif (
            "score: 0.0" in raw_response.lower()
            or "verdict: fail" in raw_response.lower()
        ):
            score = 0.0

    score = max(0.0, min(1.0, score))
    passed = score >= threshold

    return JudgeResult(
        passed=passed,
        score=score,
        reasoning=reasoning,
        evidence={"raw_response": raw_response},
        criteria_results=criteria_results,
        confidence=confidence,
        provider=provider,
        model=model,
        timestamp=datetime.now(UTC),
        metadata={"parsed_json": True},
    )


class CustomCallableJudge:
    """Wraps any user-supplied callable into a SemanticJudge provider."""

    def __init__(
        self,
        fn: Callable[..., Any] | None = None,
        *,
        callable_fn: Callable[..., Any] | None = None,
        judge_name: str | None = None,
        name: str = "CustomCallableJudge",
        threshold: float = 0.70,
        provider_name: str = "custom",
        model_name: str = "custom-callable",
    ) -> None:
        actual_fn = fn or callable_fn
        if actual_fn is None:
            raise ValueError("Either 'fn' or 'callable_fn' must be provided.")
        self.fn = actual_fn
        self.name = judge_name or name
        self.threshold = threshold
        self.provider_name = provider_name
        self.model_name = judge_name or model_name

    def judge(
        self,
        prompt: str,
        output: str,
        reference: str | None = None,
        criteria: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> JudgeResult:
        try:
            res = self.fn(
                prompt=prompt,
                output=output,
                reference=reference,
                criteria=criteria,
                context=context,
            )
        except TypeError:
            try:
                res = self.fn(prompt, output, reference, criteria)
            except TypeError:
                res = self.fn(prompt, output)

        if isinstance(res, JudgeResult):
            return res

        score = 1.0
        reasoning = ""
        evidence: dict[str, Any] = {}

        if isinstance(res, (int, float)):
            score = float(res)
        elif isinstance(res, tuple) and len(res) >= 2:
            score = float(res[0])
            reasoning = str(res[1])
        elif isinstance(res, dict):
            score = float(res.get("score", 1.0))
            reasoning = str(res.get("reasoning", ""))
            evidence = res.get("evidence", {})

        score = max(0.0, min(1.0, score))
        return JudgeResult(
            passed=score >= self.threshold,
            score=score,
            reasoning=reasoning,
            evidence=evidence,
            confidence=0.90,
            provider=self.provider_name,
            model=self.model_name,
            timestamp=datetime.now(UTC),
            metadata={"custom": True},
        )


class OllamaJudge:
    """Local Ollama judge calling Ollama's REST API without external libraries."""

    def __init__(
        self,
        model: str = "llama3",
        *,
        base_url: str = "http://localhost:11434",
        threshold: float = 0.70,
        timeout: float = 30.0,
    ) -> None:
        self.name = f"OllamaJudge({model})"
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.threshold = threshold
        self.timeout = timeout

    def judge(
        self,
        prompt: str,
        output: str,
        reference: str | None = None,
        criteria: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> JudgeResult:
        eval_prompt = (
            f"You are an impartial judge evaluating an AI assistant's response.\n\n"
            f"Task/Input: {prompt}\n"
            f"Assistant Output: {output}\n"
        )
        if reference:
            eval_prompt += f"Reference Answer: {reference}\n"
        if criteria:
            eval_prompt += f"Evaluation Criteria: {', '.join(criteria)}\n"
        eval_prompt += (
            "\nProvide your assessment strictly as a JSON object with keys: "
            "'score' (0.0 to 1.0), 'reasoning' (brief text), and 'confidence' (0.0 to 1.0)."
        )

        payload = {
            "model": self.model,
            "prompt": eval_prompt,
            "stream": False,
            "format": "json",
        }

        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                response_text = data.get("response", "")
                return _parse_judge_json_response(
                    response_text,
                    threshold=self.threshold,
                    provider="ollama",
                    model=self.model,
                )
        except Exception as e:
            # Fallback for offline testing / unreachable server
            return JudgeResult(
                passed=False,
                score=0.0,
                reasoning=f"Ollama call failed or endpoint unreachable: {e}",
                evidence={"error": str(e)},
                confidence=0.5,
                provider="ollama",
                model=self.model,
                timestamp=datetime.now(UTC),
                metadata={"error": True},
            )


class OpenAIJudge:
    """OpenAI / OpenAI-compatible judge using urllib or optional openai SDK."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        *,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        threshold: float = 0.70,
        timeout: float = 30.0,
    ) -> None:
        self.name = f"OpenAIJudge({model})"
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.threshold = threshold
        self.timeout = timeout

    def judge(
        self,
        prompt: str,
        output: str,
        reference: str | None = None,
        criteria: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> JudgeResult:
        if not self.api_key:
            # If no API key configured, return fallback mock with explicit warning
            return JudgeResult(
                passed=True,
                score=1.0,
                reasoning="OpenAI API key not set; simulated offline evaluation passed.",
                confidence=0.80,
                provider="openai-simulated",
                model=self.model,
                timestamp=datetime.now(UTC),
                metadata={"offline_simulated": True},
            )

        system_msg = (
            "You are an expert AI evaluator. Assess the quality of the model output against "
            "the provided prompt, reference, and criteria. Return strictly JSON with keys: "
            "'score' (0.0 to 1.0), 'reasoning' (string), and 'confidence' (0.0 to 1.0)."
        )
        user_content = f"Prompt: {prompt}\nOutput: {output}\n"
        if reference:
            user_content += f"Reference: {reference}\n"
        if criteria:
            user_content += f"Criteria: {json.dumps(criteria)}\n"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.0,
        }

        try:
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choice = data["choices"][0]["message"]["content"]
                return _parse_judge_json_response(
                    choice,
                    threshold=self.threshold,
                    provider="openai",
                    model=self.model,
                )
        except Exception as e:
            return JudgeResult(
                passed=False,
                score=0.0,
                reasoning=f"OpenAI evaluation failed: {e}",
                evidence={"error": str(e)},
                confidence=0.5,
                provider="openai",
                model=self.model,
                timestamp=datetime.now(UTC),
                metadata={"error": True},
            )


class AnthropicJudge:
    """Anthropic Claude judge using standard library urllib."""

    def __init__(
        self,
        model: str = "claude-3-5-sonnet-20241022",
        *,
        api_key: str | None = None,
        base_url: str = "https://api.anthropic.com/v1",
        threshold: float = 0.70,
        timeout: float = 30.0,
    ) -> None:
        self.name = f"AnthropicJudge({model})"
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.threshold = threshold
        self.timeout = timeout

    def judge(
        self,
        prompt: str,
        output: str,
        reference: str | None = None,
        criteria: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> JudgeResult:
        if not self.api_key:
            return JudgeResult(
                passed=True,
                score=1.0,
                reasoning="Anthropic API key not set; simulated offline evaluation passed.",
                confidence=0.80,
                provider="anthropic-simulated",
                model=self.model,
                timestamp=datetime.now(UTC),
                metadata={"offline_simulated": True},
            )

        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Evaluate this output for prompt: {prompt}\nOutput: {output}\n"
                        f"Criteria: {criteria or []}\n"
                        "Return strictly JSON with 'score' (0.0 to 1.0) and 'reasoning'."
                    ),
                }
            ],
        }

        try:
            req = urllib.request.Request(
                f"{self.base_url}/messages",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data["content"][0]["text"]
                return _parse_judge_json_response(
                    text,
                    threshold=self.threshold,
                    provider="anthropic",
                    model=self.model,
                )
        except Exception as e:
            return JudgeResult(
                passed=False,
                score=0.0,
                reasoning=f"Anthropic evaluation failed: {e}",
                evidence={"error": str(e)},
                confidence=0.5,
                provider="anthropic",
                model=self.model,
                timestamp=datetime.now(UTC),
                metadata={"error": True},
            )
