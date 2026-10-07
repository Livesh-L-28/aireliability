"""Deterministic generation output checks and expectations."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from aireliability.core.models import EvaluationResult, ExecutionTrace, TestCase
from aireliability.evaluation.expectations import BaseExpectation


class RegexMatch(BaseExpectation):
    """Asserts that the trace output matches a regular expression pattern."""

    def __init__(
        self,
        pattern: str,
        *,
        flags: int = 0,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or f"RegexMatch({pattern!r})",
            pattern=pattern,
            **metadata,
        )
        self.pattern = pattern
        self.flags = flags
        self._regex = re.compile(pattern, flags=flags)

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        output_str = str(trace.output) if trace.output is not None else ""
        match = self._regex.search(output_str)
        passed = match is not None

        msg = (
            f"Output matches regex pattern {self.pattern!r}."
            if passed
            else f"Output failed to match regex pattern {self.pattern!r}."
        )

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message=msg,
            evidence={
                "pattern": self.pattern,
                "matched_text": match.group(0) if match else None,
                "output": output_str,
            },
            metadata=self.metadata,
        )


class JsonValid(BaseExpectation):
    """Asserts that the trace output is valid parseable JSON."""

    def __init__(
        self,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(name=name or "JsonValid", **metadata)

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        output = trace.output
        if isinstance(output, (dict, list)):
            return EvaluationResult(
                evaluator=self.name,
                passed=True,
                score=1.0,
                message="Output is already valid JSON structured data.",
                evidence={"parsed_type": type(output).__name__},
                metadata=self.metadata,
            )

        if not isinstance(output, str):
            return EvaluationResult(
                evaluator=self.name,
                passed=False,
                score=0.0,
                message=f"Output is not a string or JSON object: {type(output).__name__}",
                evidence={"output": str(output)},
                metadata=self.metadata,
            )

        try:
            parsed = json.loads(output)
            return EvaluationResult(
                evaluator=self.name,
                passed=True,
                score=1.0,
                message="Output parsed as valid JSON successfully.",
                evidence={"parsed_type": type(parsed).__name__},
                metadata=self.metadata,
            )
        except Exception as exc:
            return EvaluationResult(
                evaluator=self.name,
                passed=False,
                score=0.0,
                message=f"Invalid JSON output: {exc}",
                evidence={"error": str(exc), "output": output},
                metadata=self.metadata,
            )


class RequiredFields(BaseExpectation):
    """Asserts that the output JSON dict contains all specified required fields."""

    def __init__(
        self,
        required_fields: list[str],
        *,
        allow_none: bool = False,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or f"RequiredFields({required_fields})",
            required_fields=required_fields,
            allow_none=allow_none,
            **metadata,
        )
        self.required_fields = list(required_fields)
        self.allow_none = allow_none

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        raw_output = trace.output
        data: dict[str, Any] | None = None

        if isinstance(raw_output, dict):
            data = raw_output
        elif isinstance(raw_output, str):
            try:
                parsed = json.loads(raw_output)
                if isinstance(parsed, dict):
                    data = parsed
            except Exception:
                data = None

        if data is None:
            return EvaluationResult(
                evaluator=self.name,
                passed=False,
                score=0.0,
                message="Output is not a valid dictionary or JSON object.",
                evidence={"output": str(raw_output)},
                metadata=self.metadata,
            )

        missing = [f for f in self.required_fields if f not in data]
        null_fields = (
            []
            if self.allow_none
            else [f for f in self.required_fields if f in data and data[f] is None]
        )

        passed = len(missing) == 0 and len(null_fields) == 0
        score = (len(self.required_fields) - len(missing) - len(null_fields)) / max(
            1, len(self.required_fields)
        )
        score = max(0.0, min(1.0, score))

        if passed:
            msg = "All required fields are present in the output."
        else:
            msg = f"Missing fields: {missing}; Null fields: {null_fields}."

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=score,
            message=msg,
            evidence={
                "required_fields": self.required_fields,
                "missing": missing,
                "null_fields": null_fields,
                "present": list(data.keys()),
            },
            metadata=self.metadata,
        )


class TypeValidation(BaseExpectation):
    """Asserts that specific keys or the entire output match designated Python types."""

    def __init__(
        self,
        expected_types: dict[str, type] | type,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(name=name or "TypeValidation", **metadata)
        self.expected_types = expected_types

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        output = trace.output

        if isinstance(self.expected_types, type):
            passed = isinstance(output, self.expected_types)
            return EvaluationResult(
                evaluator=self.name,
                passed=passed,
                score=1.0 if passed else 0.0,
                message=(
                    f"Output type {type(output).__name__} matched expected {self.expected_types.__name__}."
                    if passed
                    else f"Output type {type(output).__name__} does not match {self.expected_types.__name__}."
                ),
                evidence={"actual_type": type(output).__name__},
                metadata=self.metadata,
            )

        if not isinstance(output, dict):
            return EvaluationResult(
                evaluator=self.name,
                passed=False,
                score=0.0,
                message=f"Output is not a dict: got {type(output).__name__}",
                evidence={"output": str(output)},
                metadata=self.metadata,
            )

        mismatches: dict[str, str] = {}
        for key, exp_type in self.expected_types.items():
            if key in output and not isinstance(output[key], exp_type):
                mismatches[key] = (
                    f"expected {exp_type.__name__}, got {type(output[key]).__name__}"
                )

        passed = len(mismatches) == 0
        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message="All field types verified."
            if passed
            else f"Type mismatches: {mismatches}",
            evidence={"mismatches": mismatches},
            metadata=self.metadata,
        )


class FormatValidation(BaseExpectation):
    """Asserts that output string conforms to standard formats (email, url, uuid, datetime)."""

    FORMAT_PATTERNS = {
        "email": r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
        "date_iso": r"^\d{4}-\d{2}-\d{2}$",
        "datetime_iso": r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}",
    }

    def __init__(
        self,
        format_name: str,  # "email", "url", "uuid", "date_iso", "datetime_iso"
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or f"FormatValidation({format_name})",
            format_name=format_name,
            **metadata,
        )
        self.format_name = format_name.lower()

    def _validate(self, text: str) -> bool:
        text = text.strip()
        if self.format_name == "url":
            try:
                res = urlparse(text)
                return bool(res.scheme and res.netloc)
            except Exception:
                return False
        if self.format_name == "uuid":
            try:
                UUID(text)
                return True
            except Exception:
                return False
        if self.format_name in self.FORMAT_PATTERNS:
            return bool(re.match(self.FORMAT_PATTERNS[self.format_name], text))
        return False

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        output_str = str(trace.output) if trace.output is not None else ""
        passed = self._validate(output_str)

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message=(
                f"Output validated as format '{self.format_name}'."
                if passed
                else f"Output failed format validation '{self.format_name}'."
            ),
            evidence={"output": output_str, "format": self.format_name},
            metadata=self.metadata,
        )


class CitationPresence(BaseExpectation):
    """Asserts that output text contains citations matching brackets [1], [doc_id], or markdown links."""

    CITATION_PATTERN = re.compile(
        r"\[(?:[0-9]+|[a-zA-Z0-9_\-\.]+)\]|\([a-zA-Z0-9_\-\.]+\)"
    )

    def __init__(
        self,
        *,
        min_citations: int = 1,
        expected_sources: list[str] | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or "CitationPresence",
            min_citations=min_citations,
            expected_sources=expected_sources,
            **metadata,
        )
        self.min_citations = min_citations
        self.expected_sources = expected_sources or []

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        text = str(trace.output) if trace.output is not None else ""
        matches = self.CITATION_PATTERN.findall(text)
        found_sources = [m.strip("[]()") for m in matches]

        passed = len(matches) >= self.min_citations
        if self.expected_sources:
            found_set = set(found_sources)
            all_expected_present = all(
                src in found_set or any(src in m for m in text.split())
                for src in self.expected_sources
            )
            passed = passed and all_expected_present

        msg = (
            f"Found {len(matches)} citation(s) in output."
            if passed
            else f"Expected at least {self.min_citations} citations; found {len(matches)}."
        )

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else (len(matches) / max(1, self.min_citations)),
            message=msg,
            evidence={
                "citations_found": matches,
                "sources_found": found_sources,
                "expected_sources": self.expected_sources,
            },
            metadata=self.metadata,
        )


class CitationValidation(BaseExpectation):
    """Asserts that all cited sources in output actually exist in retrieved context documents."""

    def __init__(
        self,
        valid_sources: list[str] | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or "CitationValidation",
            valid_sources=valid_sources,
            **metadata,
        )
        self.valid_sources = list(valid_sources or [])

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        text = str(trace.output) if trace.output is not None else ""
        citations = re.findall(r"\[([a-zA-Z0-9_\-\.]+)\]", text)

        # Context document IDs from trace steps or test_case
        available_sources = set(self.valid_sources)
        if test_case and isinstance(test_case.metadata.get("context_ids"), list):
            available_sources.update(test_case.metadata["context_ids"])
        for step in trace.steps:
            if step.metadata and "doc_id" in step.metadata:
                available_sources.add(str(step.metadata["doc_id"]))
            if isinstance(step.output, list):
                for item in step.output:
                    if isinstance(item, dict) and "id" in item:
                        available_sources.add(str(item["id"]))

        invalid_citations = [
            c for c in citations if c not in available_sources and not c.isdigit()
        ]
        passed = len(invalid_citations) == 0

        score = (
            1.0
            if not citations or passed
            else max(0.0, (len(citations) - len(invalid_citations)) / len(citations))
        )

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=score,
            message=(
                "All citations valid and anchored in context."
                if passed
                else f"Hallucinated / invalid citations found: {invalid_citations}"
            ),
            evidence={
                "citations": citations,
                "invalid_citations": invalid_citations,
                "available_sources": list(available_sources),
            },
            metadata=self.metadata,
        )
