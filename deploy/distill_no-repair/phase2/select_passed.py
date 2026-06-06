#!/usr/bin/env python3
"""Select verified passing samples for solution SFT (no repair workflow)."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Verified JSONL from verify_samples.py")
    parser.add_argument("--output", required=True, help="Selected solution SFT JSONL")
    parser.add_argument("--manifest", default=None, help="Optional manifest JSON path")
    parser.add_argument("--max-per-task", type=int, default=10, help="Maximum passing samples per source task; 0 keeps all")
    parser.add_argument(
        "--min-passing-per-task",
        type=int,
        default=0,
        help="If >0, record tasks below this count as low_yield in manifest (no repair queue)",
    )
    parser.add_argument("--include-tests", action="store_true", default=True, help="Include generated tests in assistant output")
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


def source_task_id(sample: dict[str, Any]) -> str:
    meta = sample.get("meta") or {}
    source = meta.get("source_task_id")
    if isinstance(source, str) and source:
        return source
    sample_id = sample.get("id", "")
    if "_c" in sample_id:
        return sample_id.rsplit("_c", 1)[0]
    return sample_id


def candidate_number(sample: dict[str, Any]) -> int:
    candidate = sample.get("meta", {}).get("candidate")
    if isinstance(candidate, int):
        return candidate
    sample_id = sample.get("id", "")
    if "_c" in sample_id:
        suffix = sample_id.rsplit("_c", 1)[1]
        if suffix.isdigit():
            return int(suffix)
    return 0


def check_counts(sample: dict[str, Any]) -> dict[str, int]:
    phase2 = sample.get("verification", {}).get("phase2", {})
    checks = phase2.get("checks", [])
    runnable = [check for check in checks if not check.get("skipped")]
    return {
        "checks": len(checks),
        "runnable_checks": len(runnable),
        "passed_checks": sum(1 for check in runnable if check.get("ok")),
    }


def assistant_content(sample: dict[str, Any], include_tests: bool) -> str:
    code = sample.get("code", "").rstrip()
    tests = sample.get("tests", "").rstrip()
    if include_tests and tests:
        return f"{code}\n\nTests:\n{tests}"
    return code


def export_solution_row(sample: dict[str, Any], include_tests: bool) -> dict[str, Any]:
    source_id = source_task_id(sample)
    return {
        "id": f"{sample.get('id')}:solution_sft",
        "dataset_type": "solution_sft",
        "task_type": sample.get("task_type"),
        "language": sample.get("language"),
        "source": sample.get("source"),
        "source_sample_id": sample.get("id"),
        "source_task_id": source_id,
        "candidate": candidate_number(sample),
        "prompt": sample.get("prompt", ""),
        "messages": [
            {
                "role": "system",
                "content": "You are a precise TypeScript coding assistant. Return production-quality code and focused tests when requested.",
            },
            {"role": "user", "content": sample.get("prompt", "")},
            {"role": "assistant", "content": assistant_content(sample, include_tests)},
        ],
        "verification": {
            "status": sample.get("verification", {}).get("phase2", {}).get("status"),
            **check_counts(sample),
        },
        "meta": {
            "teacher": sample.get("meta", {}).get("teacher"),
            "generated_at": sample.get("meta", {}).get("generated_at"),
            "selected_at": datetime.now(timezone.utc).isoformat(),
            "selection_rule": "verified phase2 status == passed",
            "sampling": sample.get("meta", {}).get("sampling"),
        },
    }


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    manifest_path = Path(args.manifest) if args.manifest else output_path.with_suffix(".manifest.json")

    samples = load_jsonl(input_path)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        groups[source_task_id(sample)].append(sample)

    selected: list[dict[str, Any]] = []
    by_task: dict[str, dict[str, Any]] = {}
    by_type: dict[str, Counter[str]] = defaultdict(Counter)
    failure_checks = Counter()
    low_yield_groups: list[str] = []

    for group_id, group_samples in sorted(groups.items()):
        passed = [
            sample for sample in group_samples
            if sample.get("verification", {}).get("phase2", {}).get("status") == "passed"
        ]
        failed = [
            sample for sample in group_samples
            if sample.get("verification", {}).get("phase2", {}).get("status") == "failed"
        ]
        passed.sort(key=candidate_number)
        capped = passed if args.max_per_task <= 0 else passed[: args.max_per_task]
        selected.extend(capped)

        task_type = group_samples[0].get("task_type") if group_samples else None
        language = group_samples[0].get("language") if group_samples else None
        low_yield = args.min_passing_per_task > 0 and len(passed) < args.min_passing_per_task
        if low_yield:
            low_yield_groups.append(group_id)

        by_task[group_id] = {
            "task_type": task_type,
            "language": language,
            "total": len(group_samples),
            "passed": len(passed),
            "failed": len(failed),
            "selected": len(capped),
            "low_yield": low_yield,
        }
        by_type[task_type]["total"] += len(group_samples)
        by_type[task_type]["passed"] += len(passed)
        by_type[task_type]["failed"] += len(failed)
        by_type[task_type]["selected"] += len(capped)

        for sample in failed:
            for check in sample.get("verification", {}).get("phase2", {}).get("checks", []):
                if not check.get("ok") and not check.get("skipped"):
                    failure_checks[check.get("name")] += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as out:
        for sample in selected:
            out.write(json.dumps(export_solution_row(sample, args.include_tests), ensure_ascii=False) + "\n")

    passed_total = sum(1 for s in samples if s.get("verification", {}).get("phase2", {}).get("status") == "passed")
    manifest = {
        "input": str(input_path),
        "output": str(output_path),
        "total_samples": len(samples),
        "groups": len(groups),
        "passed": passed_total,
        "pass_rate": round(passed_total / len(samples), 4) if samples else 0.0,
        "selected": len(selected),
        "max_per_task": args.max_per_task,
        "min_passing_per_task": args.min_passing_per_task,
        "low_yield_groups": low_yield_groups,
        "by_task": by_task,
        "by_task_type": {key: dict(value) for key, value in sorted(by_type.items())},
        "failure_checks": dict(failure_checks.most_common()),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "total_samples": manifest["total_samples"],
        "passed": manifest["passed"],
        "pass_rate": manifest["pass_rate"],
        "selected": manifest["selected"],
        "low_yield_groups": manifest["low_yield_groups"],
    }, indent=2))


if __name__ == "__main__":
    main()
