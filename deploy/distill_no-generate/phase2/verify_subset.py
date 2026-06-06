#!/usr/bin/env python3
"""Draw a stratified subset and run the existing verify_samples harness."""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PHASE1 = Path(__file__).resolve().parents[1] / "phase1"
TRACK = Path(__file__).resolve().parents[1]
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from common import REPO, load_jsonl, write_json, write_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Filtered normalized JSONL")
    parser.add_argument("--output", required=True, help="Verified subset JSONL")
    parser.add_argument("--subset", default=None, help="Optional intermediate subset JSONL")
    parser.add_argument("--sample-size", type=int, default=50, help="Rows to verify")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--verifier", default=str(REPO / "deploy/distill_no-repair/phase2/verify_samples.py"))
    parser.add_argument("--verifier-env", default=str(REPO / "deploy/distill_no-repair/phase2/verifier.env"))
    parser.add_argument("--install-node-deps", action="store_true", default=True)
    parser.add_argument("--dry-run", action="store_true", help="Write subset only; skip verifier")
    return parser.parse_args()


def stratified_sample(rows: list[dict[str, Any]], sample_size: int, seed: int) -> list[dict[str, Any]]:
    if sample_size <= 0 or sample_size >= len(rows):
        return list(rows)

    rng = random.Random(seed)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get("task_type") or "unknown")].append(row)

    selected: list[dict[str, Any]] = []
    task_types = sorted(groups)
    per_group = max(1, sample_size // max(1, len(task_types)))
    for task_type in task_types:
        bucket = list(groups[task_type])
        rng.shuffle(bucket)
        selected.extend(bucket[:per_group])

    if len(selected) < sample_size:
        remaining = [row for row in rows if row not in selected]
        rng.shuffle(remaining)
        selected.extend(remaining[: sample_size - len(selected)])
    elif len(selected) > sample_size:
        rng.shuffle(selected)
        selected = selected[:sample_size]
    return selected


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    subset_path = Path(args.subset) if args.subset else output_path.with_name(output_path.stem + ".subset.jsonl")

    rows = load_jsonl(input_path)
    subset = stratified_sample(rows, args.sample_size, args.seed)
    write_jsonl(subset_path, subset)

    manifest = {
        "input": str(input_path),
        "subset": str(subset_path),
        "output": str(output_path),
        "sample_size": len(subset),
        "seed": args.seed,
        "by_task_type": dict(Counter(row.get("task_type") for row in subset)),
        "by_language": dict(Counter(row.get("language") for row in subset)),
    }
    write_json(subset_path.with_suffix(".manifest.json"), manifest)
    print(json.dumps(manifest, indent=2))

    if args.dry_run:
        return

    cmd = [
        sys.executable,
        str(Path(args.verifier)),
        "--env-file",
        args.verifier_env,
        "--input",
        str(subset_path),
        "--output",
        str(output_path),
    ]
    if args.install_node_deps:
        cmd.append("--install-node-deps")

    print("==> verify", " ".join(cmd), file=sys.stderr)
    env = os.environ.copy()
    venv_bin = TRACK / ".venv" / "bin"
    if venv_bin.is_dir():
        env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"
    subprocess.run(cmd, check=True, env=env)


if __name__ == "__main__":
    main()
