#!/usr/bin/env python3
"""Inspect a Sylvester-style training JSONL: row count, length stats, sources."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JSONL with {text, source, ...}")
    parser.add_argument("--show", type=int, default=3, help="Number of sample rows to print")
    parser.add_argument("--max-chars", type=int, default=400, help="Truncate sample text preview")
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


def percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    values = sorted(values)
    k = max(0, min(len(values) - 1, int(round(pct * (len(values) - 1)))))
    return values[k]


def main() -> None:
    args = parse_args()
    path = Path(args.input)
    rows = load_jsonl(path)
    if not rows:
        raise SystemExit(f"{path}: empty file")

    text_lengths = [len(row.get("text") or "") for row in rows]
    sources = Counter(row.get("source") or "unknown" for row in rows)

    # Sylvester's preprocess stores "tags" for SO and "repo"/"path" for GitHub.
    repo_counter: Counter[str] = Counter()
    tag_counter: Counter[str] = Counter()
    for row in rows:
        repo = row.get("repo")
        if isinstance(repo, str) and repo:
            repo_counter[repo] += 1
        tags = row.get("tags")
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, str):
                    tag_counter[tag] += 1
        elif isinstance(tags, str):
            tag_counter[tags] += 1

    print(f"file: {path}")
    print(f"rows: {len(rows)}")
    print("text length chars:")
    print(f"  min={min(text_lengths)} p50={percentile(text_lengths, 0.5)} "
          f"p95={percentile(text_lengths, 0.95)} max={max(text_lengths)}")
    print("source distribution:")
    for source, count in sources.most_common():
        print(f"  {source}: {count}")
    if repo_counter:
        print("top repos:")
        for repo, count in repo_counter.most_common(10):
            print(f"  {repo}: {count}")
    if tag_counter:
        print("top tags:")
        for tag, count in tag_counter.most_common(10):
            print(f"  {tag}: {count}")

    print("")
    for i, row in enumerate(rows[: args.show]):
        text = (row.get("text") or "")[: args.max_chars]
        print(f"--- row {i} (source={row.get('source')}) ---")
        print(text)
        if len(row.get("text") or "") > args.max_chars:
            print("... [truncated]")
        print("")


if __name__ == "__main__":
    main()
