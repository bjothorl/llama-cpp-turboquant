#!/usr/bin/env python3
"""Export filtered downloaded rows to solution_sft JSONL for training."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PHASE1 = Path(__file__).resolve().parents[1] / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from common import load_jsonl, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Filtered normalized JSONL")
    parser.add_argument("--output", required=True, help="solution_sft JSONL")
    parser.add_argument("--include-tests", action="store_true", help="Append tests block to assistant content")
    parser.add_argument("--max-rows", type=int, default=0, help="Cap export; 0 keeps all")
    return parser.parse_args()


def assistant_content(sample: dict[str, Any], include_tests: bool) -> str:
    code = sample.get("code", "").rstrip()
    tests = sample.get("tests", "").rstrip()
    if include_tests and tests:
        return f"{code}\n\nTests:\n{tests}"
    messages = sample.get("messages") or []
    for turn in reversed(messages):
        if turn.get("role") == "assistant":
            content = turn.get("content", "")
            if isinstance(content, str) and content.strip():
                return content.strip()
    return code


def export_row(sample: dict[str, Any], include_tests: bool) -> dict[str, Any]:
    return {
        "id": f"{sample.get('id')}:solution_sft",
        "dataset_type": "solution_sft",
        "task_type": sample.get("task_type"),
        "language": sample.get("language"),
        "source": sample.get("source"),
        "source_sample_id": sample.get("id"),
        "prompt": sample.get("prompt", ""),
        "messages": [
            {
                "role": "system",
                "content": "You are a precise coding assistant. Return production-quality code.",
            },
            {"role": "user", "content": sample.get("prompt", "")},
            {"role": "assistant", "content": assistant_content(sample, include_tests)},
        ],
        "verification": sample.get("verification"),
        "meta": {
            **(sample.get("meta") or {}),
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "selection_rule": "downloaded filtered row",
        },
    }


def main() -> None:
    args = parse_args()
    rows = load_jsonl(Path(args.input))
    if args.max_rows > 0:
        rows = rows[: args.max_rows]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as out:
        for sample in rows:
            out.write(json.dumps(export_row(sample, args.include_tests), ensure_ascii=False) + "\n")

    summary = {
        "input": str(args.input),
        "output": str(output_path),
        "exported": len(rows),
        "include_tests": args.include_tests,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(output_path.with_suffix(".manifest.json"), summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
