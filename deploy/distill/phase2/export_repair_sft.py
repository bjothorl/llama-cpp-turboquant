#!/usr/bin/env python3
"""Export successful repair attempts as a repair/review SFT dataset."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Repaired-and-reverified JSONL")
    parser.add_argument("--output", required=True, help="Output repair SFT JSONL")
    parser.add_argument("--manifest", default=None, help="Optional manifest JSON path")
    parser.add_argument("--exclude-tests-repairs", action="store_true")
    parser.add_argument("--exclude-solution-repairs", action="store_true")
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return rows


def truncate(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]..."


def successful_repair_attempt(sample: dict[str, Any]) -> dict[str, Any] | None:
    phase2 = sample.get("verification", {}).get("phase2", {})
    if phase2.get("status") != "passed":
        return None
    attempts = sample.get("meta", {}).get("repair_attempts", [])
    for attempt in reversed(attempts):
        parsed = attempt.get("parsed") or {}
        original = attempt.get("original") or {}
        result = attempt.get("result") or {}
        target = parsed.get("repair_target")
        if target not in {"solution", "tests"}:
            continue
        if not original or not result:
            continue
        before_code = original.get("code", "")
        before_tests = original.get("tests", "")
        after_code = result.get("code", "")
        after_tests = result.get("tests", "")
        if before_code == after_code and before_tests == after_tests:
            continue
        return attempt
    return None


def build_instruction(sample: dict[str, Any], attempt: dict[str, Any]) -> str:
    original = attempt.get("original") or {}
    failure = attempt.get("failure_summary") or ""
    return "\n\n".join([
        "You are a CI-aware coding review and repair agent.",
        "Classify the failure and repair only the broken part of the sample.",
        f"Task:\n{sample.get('prompt', '')}",
        f"Language:\n{sample.get('language', '')}",
        f"Current solution:\n{original.get('code', '')}",
        f"Current tests:\n{original.get('tests', '')}",
        f"Verifier failure:\n{truncate(failure)}",
    ])


def build_response(attempt: dict[str, Any]) -> dict[str, Any]:
    parsed = attempt.get("parsed") or {}
    result = attempt.get("result") or {}
    target = parsed.get("repair_target")
    return {
        "failure_cause": parsed.get("failure_cause"),
        "repair_target": target,
        "explanation": parsed.get("explanation", ""),
        "code": result.get("code", "") if target == "solution" else "",
        "tests": result.get("tests", "") if target == "tests" else "",
    }


def export_row(sample: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    parsed = attempt.get("parsed") or {}
    return {
        "id": f"{sample.get('id')}:repair:{len(sample.get('meta', {}).get('repair_attempts', []))}",
        "dataset_type": "repair_sft",
        "task_type": sample.get("task_type"),
        "language": sample.get("language"),
        "source": sample.get("source"),
        "source_sample_id": sample.get("id"),
        "source_task_id": sample.get("meta", {}).get("source_task_id"),
        "candidate": sample.get("meta", {}).get("candidate"),
        "messages": [
            {
                "role": "system",
                "content": "You are a CI-aware coding review and repair agent. Return strict JSON only.",
            },
            {
                "role": "user",
                "content": build_instruction(sample, attempt),
            },
            {
                "role": "assistant",
                "content": json.dumps(build_response(attempt), ensure_ascii=False),
            },
        ],
        "repair": {
            "failure_cause": parsed.get("failure_cause"),
            "repair_target": parsed.get("repair_target"),
            "http_status": attempt.get("http_status"),
            "latency_s": attempt.get("latency_s"),
            "generated_at": attempt.get("generated_at"),
        },
        "meta": {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "input_verification_status": "passed",
            "rule": "include only repairs whose final sample verifies successfully",
        },
    }


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    manifest_path = Path(args.manifest) if args.manifest else output_path.with_suffix(".manifest.json")
    samples = load_jsonl(input_path)

    rows: list[dict[str, Any]] = []
    skipped = Counter()
    by_target = Counter()
    by_cause = Counter()
    for sample in samples:
        attempt = successful_repair_attempt(sample)
        if attempt is None:
            skipped["no_successful_repair"] += 1
            continue
        parsed = attempt.get("parsed") or {}
        target = parsed.get("repair_target")
        if target == "solution" and args.exclude_solution_repairs:
            skipped["solution_repair_excluded"] += 1
            continue
        if target == "tests" and args.exclude_tests_repairs:
            skipped["tests_repair_excluded"] += 1
            continue
        rows.append(export_row(sample, attempt))
        by_target[target] += 1
        by_cause[parsed.get("failure_cause")] += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")

    manifest = {
        "input": str(input_path),
        "output": str(output_path),
        "total_samples": len(samples),
        "exported": len(rows),
        "skipped": dict(skipped),
        "by_repair_target": dict(by_target),
        "by_failure_cause": dict(by_cause),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
