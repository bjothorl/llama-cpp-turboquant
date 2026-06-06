#!/usr/bin/env python3
"""Filter normalized JSONL: language, length, dedup, benchmark leakage."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PHASE1 = Path(__file__).resolve().parent
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from common import REPO, TRACK, fingerprint, load_jsonl, write_json, write_jsonl


BENCHMARK_SOURCES = (
    ("openai/openai_humaneval", "test", "prompt"),
    ("google-research-datasets/mbpp", "train", "text"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Normalized JSONL")
    parser.add_argument("--output", required=True, help="Filtered JSONL")
    parser.add_argument("--languages", default="python,typescript", help="Comma-separated allowlist")
    parser.add_argument("--max-prompt-chars", type=int, default=12000)
    parser.add_argument("--max-code-chars", type=int, default=24000)
    parser.add_argument("--max-tests-chars", type=int, default=24000)
    parser.add_argument("--skip-benchmark-check", action="store_true")
    parser.add_argument("--skip-cross-track-dedup", action="store_true")
    parser.add_argument(
        "--cross-track",
        default=str(REPO / "deploy/distill_no-repair/phase2/outputs/solution_sft.jsonl"),
        help="Optional local-gen SFT JSONL for exact prompt dedup",
    )
    return parser.parse_args()


def load_benchmark_fingerprints(cache_dir: Path) -> set[str]:
    cache_path = cache_dir / "benchmark_prompts.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text())
        return set(payload.get("fingerprints", []))

    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit("benchmark check requires `datasets`; use --skip-benchmark-check to bypass") from exc

    fingerprints: set[str] = set()
    for dataset_id, split, field in BENCHMARK_SOURCES:
        ds = load_dataset(dataset_id, split=split, streaming=True)
        for row in ds:
            text = row.get(field)
            if isinstance(text, str) and text.strip():
                fingerprints.add(fingerprint(text))
        print(f"loaded benchmark prompts from {dataset_id}", file=sys.stderr)

    write_json(cache_path, {"fingerprints": sorted(fingerprints)})
    return fingerprints


def load_cross_track_fingerprints(path: Path) -> set[str]:
    if not path.exists():
        return set()
    fps: set[str] = set()
    for row in load_jsonl(path):
        prompt = row.get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            fps.add(fingerprint(prompt))
    return fps


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    allowed = {lang.strip().lower() for lang in args.languages.split(",") if lang.strip()}

    rows = load_jsonl(input_path)
    benchmark_fps = set()
    if not args.skip_benchmark_check:
        benchmark_fps = load_benchmark_fingerprints(TRACK / "phase1/cache/benchmarks")

    cross_track_fps = set()
    if not args.skip_cross_track_dedup:
        cross_track_fps = load_cross_track_fingerprints(Path(args.cross_track))

    kept: list[dict[str, Any]] = []
    dropped = Counter()
    seen_prompts: set[str] = set()

    for row in rows:
        language = str(row.get("language", "")).lower()
        if language not in allowed:
            dropped["language"] += 1
            continue

        prompt = row.get("prompt", "")
        code = row.get("code", "")
        tests = row.get("tests", "")
        if len(prompt) > args.max_prompt_chars:
            dropped["prompt_length"] += 1
            continue
        if len(code) > args.max_code_chars:
            dropped["code_length"] += 1
            continue
        if len(tests) > args.max_tests_chars:
            dropped["tests_length"] += 1
            continue
        if not code.strip():
            dropped["empty_code"] += 1
            continue

        fp = row.get("meta", {}).get("prompt_fingerprint") or fingerprint(prompt)
        if fp in seen_prompts:
            dropped["duplicate_prompt"] += 1
            continue
        if benchmark_fps and fp in benchmark_fps:
            dropped["benchmark_leak"] += 1
            continue
        if cross_track_fps and fp in cross_track_fps:
            dropped["cross_track_duplicate"] += 1
            continue

        seen_prompts.add(fp)
        kept.append(row)

    write_jsonl(output_path, kept)
    by_language = Counter(row.get("language") for row in kept)
    by_task_type = Counter(row.get("task_type") for row in kept)
    summary = {
        "input": str(input_path),
        "output": str(output_path),
        "input_rows": len(rows),
        "kept": len(kept),
        "dropped": dict(dropped),
        "by_language": dict(by_language),
        "by_task_type": dict(by_task_type.most_common(20)),
    }
    write_json(output_path.with_suffix(".summary.json"), summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
