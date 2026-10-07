"""Dataset manager providing validation, diffing, import, and export."""

from __future__ import annotations

import contextlib
import csv
import json
from pathlib import Path
from typing import Any

from aireliability.core.models import TestCase
from aireliability.evaluation.datasets.models import DatasetSplit, EvaluationDataset


def validate_dataset(dataset: EvaluationDataset) -> list[str]:
    """Validate dataset integrity and return list of validation errors/warnings."""
    errors: list[str] = []
    if not dataset.name or not dataset.name.strip():
        errors.append("Dataset name must not be empty.")
    if not dataset.id or not dataset.id.strip():
        errors.append("Dataset ID must not be empty.")

    case_ids: set[str] = set()
    for idx, tc in enumerate(dataset.test_cases):
        if not tc.id:
            errors.append(f"TestCase at index {idx} has an empty ID.")
        elif tc.id in case_ids:
            errors.append(f"Duplicate TestCase ID detected: '{tc.id}'.")
        case_ids.add(tc.id)

        if tc.input is None or (isinstance(tc.input, str) and not tc.input.strip()):
            errors.append(f"TestCase '{tc.id}' has empty input.")

    return errors


def compare_datasets(
    dataset_a: EvaluationDataset,
    dataset_b: EvaluationDataset,
) -> dict[str, Any]:
    """Compare two datasets and return added, removed, and modified test cases."""
    map_a = {tc.id: tc for tc in dataset_a.test_cases}
    map_b = {tc.id: tc for tc in dataset_b.test_cases}

    added_ids = sorted(set(map_b.keys()) - set(map_a.keys()))
    removed_ids = sorted(set(map_a.keys()) - set(map_b.keys()))
    common_ids = sorted(set(map_a.keys()).intersection(set(map_b.keys())))

    modified: list[dict[str, Any]] = []
    for cid in common_ids:
        tc_a = map_a[cid]
        tc_b = map_b[cid]
        changes: list[str] = []
        if tc_a.input != tc_b.input:
            changes.append("input")
        if tc_a.expected_output != tc_b.expected_output:
            changes.append("expected_output")
        if tc_a.expectations != tc_b.expectations:
            changes.append("expectations")
        if tc_a.tags != tc_b.tags:
            changes.append("tags")
        if changes:
            modified.append({"test_id": cid, "changed_fields": changes})

    return {
        "dataset_a_version": dataset_a.version,
        "dataset_b_version": dataset_b.version,
        "total_a": len(dataset_a.test_cases),
        "total_b": len(dataset_b.test_cases),
        "added_count": len(added_ids),
        "added_ids": added_ids,
        "added": added_ids,
        "removed_count": len(removed_ids),
        "removed_ids": removed_ids,
        "removed": removed_ids,
        "modified_count": len(modified),
        "modified": modified,
    }


class DatasetManager:
    """Manages loading, saving, validation, comparison, and export of evaluation datasets."""

    @staticmethod
    def load(file_path: Path | str) -> EvaluationDataset:
        """Load an EvaluationDataset from JSON file."""
        path = Path(file_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return EvaluationDataset.model_validate(data)

    @staticmethod
    def save(dataset: EvaluationDataset, file_path: Path | str) -> None:
        """Save EvaluationDataset to JSON file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dataset.model_dump_json(indent=2), encoding="utf-8")

    @staticmethod
    def export_jsonl(dataset: EvaluationDataset, file_path: Path | str) -> None:
        """Export dataset test cases to JSONL format."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [tc.model_dump_json() for tc in dataset.test_cases]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def export_csv(dataset: EvaluationDataset, file_path: Path | str) -> None:
        """Export dataset test cases to CSV format."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = ["id", "name", "input", "expected_output", "expectations", "tags"]
        with open(path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for tc in dataset.test_cases:
                writer.writerow(
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "input": json.dumps(tc.input)
                        if not isinstance(tc.input, str)
                        else tc.input,
                        "expected_output": (
                            json.dumps(tc.expected_output)
                            if not isinstance(tc.expected_output, str)
                            else tc.expected_output
                        ),
                        "expectations": ";".join(tc.expectations),
                        "tags": ";".join(tc.tags),
                    }
                )

    @staticmethod
    def import_jsonl(
        file_path: Path | str,
        name: str,
        *,
        id: str | None = None,
        split: DatasetSplit = DatasetSplit.TEST,
    ) -> EvaluationDataset:
        """Import test cases from JSONL into an EvaluationDataset."""
        path = Path(file_path)
        test_cases: list[TestCase] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line_str = line.strip()
            if line_str:
                data = json.loads(line_str)
                test_cases.append(TestCase.model_validate(data))
        ds_id = id or f"ds_{path.stem}"
        return EvaluationDataset(
            id=ds_id,
            name=name,
            split=split,
            test_cases=test_cases,
        )

    @staticmethod
    def import_csv(
        file_path: Path | str,
        name: str,
        *,
        id: str | None = None,
        split: DatasetSplit = DatasetSplit.TEST,
    ) -> EvaluationDataset:
        """Import test cases from CSV file into an EvaluationDataset."""
        path = Path(file_path)
        test_cases: list[TestCase] = []
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                inp: Any = row.get("input", "")
                exp_out: Any = row.get("expected_output")
                with contextlib.suppress(Exception):
                    inp = json.loads(inp)
                if exp_out:
                    with contextlib.suppress(Exception):
                        exp_out = json.loads(exp_out)
                expectations = [
                    x.strip()
                    for x in row.get("expectations", "").split(";")
                    if x.strip()
                ]
                tags = [x.strip() for x in row.get("tags", "").split(";") if x.strip()]
                test_cases.append(
                    TestCase(
                        id=row.get("id") or f"tc_{len(test_cases) + 1}",
                        name=row.get("name") or f"test_{len(test_cases) + 1}",
                        input=inp,
                        expected_output=exp_out,
                        expectations=expectations,
                        tags=tags,
                    )
                )
        ds_id = id or f"ds_{path.stem}"
        return EvaluationDataset(
            id=ds_id,
            name=name,
            split=split,
            test_cases=test_cases,
        )

    # Convenience method aliases
    export_to_json = save
    load_from_json = load
    export_to_jsonl = export_jsonl
    load_from_jsonl = import_jsonl
    export_to_csv = export_csv
    load_from_csv = import_csv
