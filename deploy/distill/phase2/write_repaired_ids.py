#!/usr/bin/env python3
"""Write sample IDs that have repair metadata in a repaired JSONL file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Repaired JSONL")
    parser.add_argument("--output", required=True, help="Output newline-delimited ID file")
    parser.add_argument("--applied-only", action="store_true", help="Only include repair attempts that changed code or tests")
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


def has_repair(row: dict[str, Any]) -> bool:
    if row.get("verification", {}).get("repair"):
        return True
    return bool(row.get("meta", {}).get("repair_attempts"))


def repair_applied(row: dict[str, Any]) -> bool:
    repair = row.get("verification", {}).get("repair")
    if repair:
        return bool(repair.get("applied"))
    attempts = row.get("meta", {}).get("repair_attempts") or []
    if not attempts:
        return False
    latest = attempts[-1]
    original = latest.get("original") or {}
    result = latest.get("result") or {}
    return original.get("code") != result.get("code") or original.get("tests") != result.get("tests")


def main() -> None:
    args = parse_args()
    rows = load_jsonl(Path(args.input))
    ids: list[str] = []
    for row in rows:
        if not has_repair(row):
            continue
        if args.applied_only and not repair_applied(row):
            continue
        ids.append(row["id"])

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(ids) + ("\n" if ids else ""))
    print(json.dumps({
        "input": args.input,
        "output": str(output_path),
        "ids": len(ids),
        "applied_only": args.applied_only,
    }, indent=2))


if __name__ == "__main__":
    main()
