#!/usr/bin/env python3
"""Run a coding smoke set against llama-server and extract MTP stats.

Delegates the actual HTTP loop to deploy/distill/phase0/run_smoke.py so the
request format stays consistent with the existing Phase 0 baseline. Then
parses responses.jsonl for speculative-decoding metrics that llama-server
includes in `timings` when --spec-type draft-mtp is active.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PHASE_DIR = Path(__file__).resolve().parent
PHASE0_SMOKE = ROOT / "deploy/distill/phase0/run_smoke.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True,
                        help="Run label (e.g. 'baseline' or 'trained'); used as runs/<label>/")
    parser.add_argument("--prompts", required=True, help="Smoke prompt JSONL")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="8080")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--run-dir", default=None,
                        help="Override default runs/<label>/")
    return parser.parse_args()


def collect_mtp_stats(responses_path: Path) -> dict[str, Any]:
    """Pull speculative-decoding fields out of each response timings block.

    llama-server reports keys like `n_drafted`, `n_accepted`, `draft_n` and
    `draft_n_accepted` depending on build. We collect whichever are present.
    """
    per_prompt = []
    totals = {
        "n_drafted": 0,
        "n_accepted": 0,
        "predicted_n": 0,
        "predicted_ms": 0.0,
    }
    saw_any = False
    for line in responses_path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        timings = (row.get("metrics") or {}).get("timings") or {}
        n_draft = timings.get("n_drafted")
        if n_draft is None:
            n_draft = timings.get("draft_n")
        n_accept = timings.get("n_accepted")
        if n_accept is None:
            n_accept = timings.get("draft_n_accepted")
        predicted_n = timings.get("predicted_n")
        predicted_ms = timings.get("predicted_ms")

        if n_draft is not None and n_accept is not None:
            saw_any = True
            totals["n_drafted"] += int(n_draft)
            totals["n_accepted"] += int(n_accept)
        if predicted_n is not None:
            totals["predicted_n"] += int(predicted_n)
        if predicted_ms is not None:
            totals["predicted_ms"] += float(predicted_ms)

        per_prompt.append({
            "id": row.get("id"),
            "category": row.get("category"),
            "http_status": row.get("http_status"),
            "latency_s": row.get("latency_s"),
            "tokens_per_second": (row.get("metrics") or {}).get("tokens_per_second"),
            "n_drafted": n_draft,
            "n_accepted": n_accept,
            "predicted_n": predicted_n,
        })

    acceptance = (
        totals["n_accepted"] / totals["n_drafted"]
        if saw_any and totals["n_drafted"] > 0
        else None
    )
    overall_tps = (
        totals["predicted_n"] / (totals["predicted_ms"] / 1000.0)
        if totals["predicted_ms"] > 0
        else None
    )

    return {
        "saw_mtp_fields": saw_any,
        "totals": totals,
        "mtp_accept_ratio": acceptance,
        "overall_tokens_per_second": overall_tps,
        "per_prompt": per_prompt,
    }


def main() -> None:
    args = parse_args()
    run_dir = Path(args.run_dir) if args.run_dir else PHASE_DIR / "runs" / args.label
    run_dir.mkdir(parents=True, exist_ok=True)

    if not PHASE0_SMOKE.is_file():
        raise SystemExit(f"missing phase0 smoke script: {PHASE0_SMOKE}")

    print(f"running phase0 smoke against {args.host}:{args.port} -> {run_dir}")
    cmd = [
        sys.executable,
        str(PHASE0_SMOKE),
        "--run-dir", str(run_dir),
        "--prompts", args.prompts,
        "--host", args.host,
        "--port", args.port,
        "--max-tokens", str(args.max_tokens),
        "--temperature", str(args.temperature),
    ]
    subprocess.run(cmd, check=True)

    responses_path = run_dir / "responses.jsonl"
    if not responses_path.is_file():
        raise SystemExit(f"phase0 smoke did not produce {responses_path}")

    mtp = collect_mtp_stats(responses_path)
    mtp_summary = {
        "label": args.label,
        "prompts": args.prompts,
        "host": args.host,
        "port": args.port,
        **mtp,
    }
    out_path = run_dir / "mtp_summary.json"
    out_path.write_text(json.dumps(mtp_summary, indent=2) + "\n")

    print(json.dumps({
        "label": args.label,
        "saw_mtp_fields": mtp["saw_mtp_fields"],
        "mtp_accept_ratio": mtp["mtp_accept_ratio"],
        "overall_tokens_per_second": mtp["overall_tokens_per_second"],
        "total_drafted": mtp["totals"]["n_drafted"],
        "total_accepted": mtp["totals"]["n_accepted"],
        "summary_path": str(out_path),
    }, indent=2))

    if not mtp["saw_mtp_fields"]:
        print("WARNING: no n_drafted/n_accepted fields in any response.", file=sys.stderr)
        print("  Check that the server was started with --spec-type draft-mtp", file=sys.stderr)
        print("  and that the GGUF has nextn_predict_layers > 0.", file=sys.stderr)


if __name__ == "__main__":
    main()
