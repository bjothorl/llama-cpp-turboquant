#!/usr/bin/env python3
"""Normalize cached HF rows into the local distill JSONL schema."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

PHASE1 = Path(__file__).resolve().parent
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from common import dataset_config, load_jsonl, slugify_dataset_id, write_json, write_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_id", help="Hugging Face dataset id")
    parser.add_argument("--cache", default=None, help="Cache directory with raw.jsonl + manifest.json")
    parser.add_argument("--out", default=None, help="Normalized JSONL output path")
    parser.add_argument("--revision", default=None, help="Override revision recorded in output metadata")
    return parser.parse_args()


def load_normalizer(name: str):
    module = importlib.import_module(f"normalizers.{name}")
    if not hasattr(module, "normalize_row"):
        raise SystemExit(f"normalizer {name!r} missing normalize_row()")
    return module


def main() -> None:
    args = parse_args()
    cfg = dataset_config(args.dataset_id)
    slug = slugify_dataset_id(args.dataset_id)
    cache_dir = Path(args.cache) if args.cache else Path(__file__).resolve().parent / "cache" / slug
    raw_path = cache_dir / "raw.jsonl"
    manifest_path = cache_dir / "manifest.json"
    if not raw_path.exists():
        raise SystemExit(f"missing cache: {raw_path}. Run phase1/download.py first.")

    revision = args.revision or cfg["revision"]
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        revision = args.revision or manifest.get("revision") or revision

    normalizer = load_normalizer(cfg["normalizer"])
    out_path = Path(args.out) if args.out else Path(__file__).resolve().parent / "outputs" / f"{slug}.jsonl"

    normalized: list[dict[str, Any]] = []
    skipped = 0
    for row_index, row in enumerate(load_jsonl(raw_path)):
        sample = normalizer.normalize_row(
            row,
            dataset_id=args.dataset_id,
            revision=revision,
            license_name=cfg["license"],
            uri=cfg["uri"],
            row_index=row_index,
        )
        if sample is None:
            skipped += 1
            continue
        normalized.append(sample)

    count = write_jsonl(out_path, normalized)
    summary = {
        "dataset_id": args.dataset_id,
        "revision": revision,
        "input": str(raw_path),
        "output": str(out_path),
        "normalized": count,
        "skipped": skipped,
    }
    write_json(out_path.with_suffix(".summary.json"), summary)
    print(f"normalized {count} rows -> {out_path} (skipped {skipped})")


if __name__ == "__main__":
    main()
