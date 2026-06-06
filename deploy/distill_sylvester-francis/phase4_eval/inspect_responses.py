#!/usr/bin/env python3
"""Inspect responses.jsonl produced by deploy/distill/phase0/run_smoke.py.

Usage examples:

  # Single run, short previews of all prompts
  inspect_responses.py --run deploy/distill_sylvester-francis/phase4_eval/runs/trained

  # Side-by-side baseline vs trained
  inspect_responses.py \\
      --run    deploy/distill_sylvester-francis/phase4_eval/runs/trained \\
      --baseline deploy/distill_sylvester-francis/phase4_eval/runs/baseline

  # Full content for one prompt
  inspect_responses.py --run .../runs/trained --id ts_bugfix_001 --full
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True, help="Run dir (containing responses.jsonl)")
    parser.add_argument("--baseline", default=None, help="Optional baseline run dir for side-by-side")
    parser.add_argument("--id", default=None, help="Show only this prompt id")
    parser.add_argument("--full", action="store_true", help="Print full content (no truncation)")
    parser.add_argument("--preview", type=int, default=600, help="Preview chars when not --full")
    parser.add_argument("--show-reasoning", action="store_true",
                        help="Also print the reasoning_content field")
    return parser.parse_args()


def load_responses(run_dir: Path) -> dict[str, dict[str, Any]]:
    path = run_dir / "responses.jsonl"
    if not path.is_file():
        raise SystemExit(f"missing: {path}")
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[row.get("id") or f"_{len(out)}"] = row
    return out


def message_fields(row: dict[str, Any]) -> tuple[str, str]:
    choices = ((row.get("response") or {}).get("choices") or [{}])
    msg = choices[0].get("message") or {}
    return (msg.get("content") or "", msg.get("reasoning_content") or "")


def metric_fields(row: dict[str, Any]) -> dict[str, Any]:
    metrics = row.get("metrics") or {}
    timings = metrics.get("timings") or {}
    n_drafted = timings.get("n_drafted")
    n_accepted = timings.get("n_accepted")
    if n_drafted is None:
        n_drafted = timings.get("draft_n")
    if n_accepted is None:
        n_accepted = timings.get("draft_n_accepted")
    return {
        "tps": metrics.get("tokens_per_second"),
        "predicted_n": timings.get("predicted_n"),
        "n_drafted": n_drafted,
        "n_accepted": n_accepted,
    }


def truncate(text: str, limit: int, full: bool) -> str:
    if full or len(text) <= limit:
        return text
    return text[:limit] + f"\n... [+{len(text) - limit} chars]"


def render_one(label: str, row: dict[str, Any], preview: int, full: bool, show_reasoning: bool) -> None:
    content, reasoning = message_fields(row)
    m = metric_fields(row)
    accept = (
        f"{m['n_accepted']}/{m['n_drafted']} ({m['n_accepted'] / m['n_drafted']:.2%})"
        if m["n_drafted"] else "n/a"
    )
    print(f"-- [{label}]  chars={len(content)}  predicted={m['predicted_n']}  "
          f"accept={accept}  tps={m['tps']:.1f}" if m['tps'] is not None else
          f"-- [{label}]  chars={len(content)}  predicted={m['predicted_n']}  "
          f"accept={accept}  tps=n/a")
    if show_reasoning and reasoning:
        print("   reasoning:")
        print(truncate(reasoning, preview, full))
        print("   --- content ---")
    print(truncate(content, preview, full))


def main() -> None:
    args = parse_args()

    run = load_responses(Path(args.run))
    baseline = load_responses(Path(args.baseline)) if args.baseline else None

    ids = list(run.keys())
    if args.id:
        if args.id not in run:
            raise SystemExit(f"id {args.id!r} not in {args.run}")
        ids = [args.id]

    for prompt_id in ids:
        row = run[prompt_id]
        category = row.get("category") or "?"
        print("=" * 80)
        print(f"{prompt_id}  ({category})")

        if baseline and prompt_id in baseline:
            render_one("baseline", baseline[prompt_id], args.preview, args.full, args.show_reasoning)
            print()
            render_one("trained ", row, args.preview, args.full, args.show_reasoning)
        else:
            render_one("trained ", row, args.preview, args.full, args.show_reasoning)


if __name__ == "__main__":
    main()
