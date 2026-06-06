#!/usr/bin/env python3
"""Summarize per-task and per-type pass rates from verified JSONL."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Verified JSONL")
    parser.add_argument("--manifest", default=None, help="Optional select_passed manifest for failure_checks")
    parser.add_argument("--output", default=None, help="Optional text report path")
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


def phase2_status(sample: dict[str, Any]) -> str:
    return (sample.get("verification") or {}).get("phase2", {}).get("status", "missing")


def tier(sample: dict[str, Any]) -> str:
    return (sample.get("source") or {}).get("tier", "unknown")


def main() -> None:
    args = parse_args()
    samples = load_jsonl(Path(args.input))
    by_task: dict[str, Counter[str]] = defaultdict(Counter)
    by_type: dict[str, Counter[str]] = defaultdict(Counter)
    by_tier: dict[str, Counter[str]] = defaultdict(Counter)
    failure_checks = Counter()

    for sample in samples:
        status = phase2_status(sample)
        tid = source_task_id(sample)
        task_type = sample.get("task_type", "unknown")
        by_task[tid][status] += 1
        by_type[task_type][status] += 1
        by_tier[tier(sample)][status] += 1
        if status == "failed":
            for check in (sample.get("verification") or {}).get("phase2", {}).get("checks", []):
                if not check.get("ok") and not check.get("skipped"):
                    failure_checks[check.get("name")] += 1

    total = len(samples)
    passed = sum(1 for s in samples if phase2_status(s) == "passed")
    failed = sum(1 for s in samples if phase2_status(s) == "failed")
    unverified = total - passed - failed

    lines = [
        f"input: {args.input}",
        f"total: {total}",
        f"passed: {passed} ({100 * passed / total:.1f}%)" if total else "passed: 0",
        f"failed: {failed}",
        f"unverified: {unverified}",
        "",
        "by_task_type:",
    ]
    for task_type, counts in sorted(by_type.items()):
        p = counts.get("passed", 0)
        t = sum(counts.values())
        lines.append(f"  {task_type}: {p}/{t} ({100 * p / t:.1f}%)" if t else f"  {task_type}: 0/0")

    lines.append("")
    lines.append("by_tier:")
    for tr, counts in sorted(by_tier.items()):
        p = counts.get("passed", 0)
        t = sum(counts.values())
        lines.append(f"  {tr}: {p}/{t} ({100 * p / t:.1f}%)" if t else f"  {tr}: 0/0")

    lines.append("")
    lines.append("by_task (sorted by pass rate):")
    task_rows = []
    for tid, counts in by_task.items():
        p = counts.get("passed", 0)
        t = sum(counts.values())
        task_rows.append((p / t if t else 0.0, tid, p, t))
    for rate, tid, p, t in sorted(task_rows):
        lines.append(f"  {tid}: {p}/{t} ({100 * rate:.1f}%)")

    if failure_checks:
        lines.append("")
        lines.append("top_failure_checks:")
        for name, count in failure_checks.most_common(10):
            lines.append(f"  {name}: {count}")

    if args.manifest:
        manifest_path = Path(args.manifest)
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            lines.append("")
            lines.append(f"manifest_selected: {manifest.get('selected')}")
            lines.append(f"manifest_low_yield_groups: {manifest.get('low_yield_groups')}")

    report = "\n".join(lines)
    print(report)
    if args.output:
        Path(args.output).write_text(report + "\n")


if __name__ == "__main__":
    main()
