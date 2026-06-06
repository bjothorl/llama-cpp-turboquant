#!/usr/bin/env python3
"""Compare two mtp_summary.json files and check the PLAN.md acceptance gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


GATE_RATIO = 0.80  # trained MTP acceptance must stay >= 80% of baseline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True,
                        help="phase4_eval/runs/baseline/mtp_summary.json")
    parser.add_argument("--trained", required=True,
                        help="phase4_eval/runs/trained/mtp_summary.json")
    parser.add_argument("--gate", type=float, default=GATE_RATIO,
                        help=f"Min trained/baseline acceptance ratio (default {GATE_RATIO})")
    return parser.parse_args()


def load(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"missing summary: {path}")
    return json.loads(path.read_text())


def fmt_ratio(value):
    return f"{value:.4f}" if isinstance(value, (int, float)) else "n/a"


def main() -> None:
    args = parse_args()
    base = load(Path(args.baseline))
    trained = load(Path(args.trained))

    b_accept = base.get("mtp_accept_ratio")
    t_accept = trained.get("mtp_accept_ratio")
    b_tps = base.get("overall_tokens_per_second")
    t_tps = trained.get("overall_tokens_per_second")

    accept_ratio_ratio = None
    accept_gate_ok = None
    if isinstance(b_accept, (int, float)) and b_accept > 0 and isinstance(t_accept, (int, float)):
        accept_ratio_ratio = t_accept / b_accept
        accept_gate_ok = accept_ratio_ratio >= args.gate

    tps_ratio = None
    if isinstance(b_tps, (int, float)) and b_tps > 0 and isinstance(t_tps, (int, float)):
        tps_ratio = t_tps / b_tps

    print("MTP acceptance comparison")
    print("-" * 60)
    print(f"  baseline label : {base.get('label')}")
    print(f"  trained  label : {trained.get('label')}")
    print()
    print(f"  baseline saw_mtp_fields: {base.get('saw_mtp_fields')}")
    print(f"  trained  saw_mtp_fields: {trained.get('saw_mtp_fields')}")
    print()
    print(f"  baseline accept ratio   : {fmt_ratio(b_accept)}")
    print(f"  trained  accept ratio   : {fmt_ratio(t_accept)}")
    print(f"  trained / baseline      : {fmt_ratio(accept_ratio_ratio)}")
    print(f"  acceptance gate ({args.gate:.2f}): "
          f"{'PASS' if accept_gate_ok else 'FAIL' if accept_gate_ok is False else 'n/a'}")
    print()
    print(f"  baseline overall tok/s  : {fmt_ratio(b_tps)}")
    print(f"  trained  overall tok/s  : {fmt_ratio(t_tps)}")
    print(f"  trained / baseline tok/s: {fmt_ratio(tps_ratio)}")

    if not base.get("saw_mtp_fields") or not trained.get("saw_mtp_fields"):
        print("\nWARNING: one or both runs lacked MTP fields. Check server start args.")

    raise SystemExit(0 if accept_gate_ok is not False else 1)


if __name__ == "__main__":
    main()
