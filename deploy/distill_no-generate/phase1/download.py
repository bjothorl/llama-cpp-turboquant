#!/usr/bin/env python3
"""Download a pinned Hugging Face dataset slice to local cache JSONL."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

PHASE1 = Path(__file__).resolve().parent
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from common import append_jsonl, dataset_config, slugify_dataset_id, write_json


DEFAULT_PARQUET = "data/train-00000-of-00005.parquet"
DEFAULT_TRAIN_SHARDS = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_id", help="Hugging Face dataset id, e.g. KodCode/KodCode-V1-SFT-4o")
    parser.add_argument("--revision", default=None, help="Git revision; defaults to phase1/datasets.json pin")
    parser.add_argument("--out", default=None, help="Cache directory (default: phase1/cache/<slug>/)")
    parser.add_argument("--split", default=None, help="Dataset split (default from datasets.json or train)")
    parser.add_argument("--max-rows", type=int, default=1000, help="Maximum raw rows to write per shard (0 = all in shard)")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing raw.jsonl")
    parser.add_argument(
        "--all-train-shards",
        action="store_true",
        help="Download all train parquet shards (train-00000-of-0000N … train-0000(N-1)-of-0000N)",
    )
    parser.add_argument(
        "--train-shards",
        type=int,
        default=DEFAULT_TRAIN_SHARDS,
        help="Shard count when --all-train-shards is set",
    )
    parser.add_argument(
        "--mode",
        choices=("parquet", "stream"),
        default="parquet",
        help="parquet = one HF parquet shard (stable); stream = datasets streaming API",
    )
    parser.add_argument("--parquet-file", default=DEFAULT_PARQUET, help="Repo-relative parquet path for --mode parquet")
    return parser.parse_args()


def train_shard_path(shard_index: int, shard_count: int) -> str:
    return f"data/train-{shard_index:05d}-of-{shard_count:05d}.parquet"


def iter_parquet_rows(dataset_id: str, revision: str, parquet_file: str, max_rows: int) -> Iterator[dict[str, Any]]:
    try:
        import pyarrow.parquet as pq
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise SystemExit(
            "missing dependency: pyarrow/huggingface_hub. Install deploy/distill_no-generate/requirements.txt"
        ) from exc

    local_path = hf_hub_download(
        repo_id=dataset_id,
        repo_type="dataset",
        filename=parquet_file,
        revision=revision,
    )
    table = pq.read_table(local_path)
    count = 0
    for batch in table.to_batches(max_chunksize=64):
        for row in batch.to_pylist():
            yield row
            count += 1
            if max_rows and count >= max_rows:
                return


def iter_stream_rows(dataset_id: str, revision: str, split: str, max_rows: int) -> Iterator[dict[str, Any]]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit("missing dependency: datasets") from exc

    ds = load_dataset(dataset_id, split=split, streaming=True, revision=revision)
    count = 0
    for row in ds:
        yield row
        count += 1
        if max_rows and count >= max_rows:
            return


def main() -> None:
    args = parse_args()
    cfg = dataset_config(args.dataset_id)
    revision = args.revision or cfg["revision"]
    split = args.split or cfg.get("split", "train")
    slug = slugify_dataset_id(args.dataset_id)
    out_dir = Path(args.out) if args.out else PHASE1 / "cache" / slug
    raw_path = out_dir / "raw.jsonl"
    manifest_path = out_dir / "manifest.json"

    if raw_path.exists() and not args.overwrite:
        raise SystemExit(f"{raw_path} exists; pass --overwrite to replace")

    out_dir.mkdir(parents=True, exist_ok=True)
    if raw_path.exists():
        raw_path.unlink()

    parquet_files: list[str]
    if args.all_train_shards:
        if args.mode != "parquet":
            raise SystemExit("--all-train-shards requires --mode parquet")
        parquet_files = [train_shard_path(i, args.train_shards) for i in range(args.train_shards)]
    else:
        parquet_files = [args.parquet_file]

    row_count = 0
    for parquet_file in parquet_files:
        print(f"downloading {parquet_file}...", file=sys.stderr)
        if args.mode == "parquet":
            rows = iter_parquet_rows(args.dataset_id, revision, parquet_file, args.max_rows)
        else:
            rows = iter_stream_rows(args.dataset_id, revision, split, args.max_rows)

        shard_rows = 0
        for row in rows:
            append_jsonl(raw_path, row)
            row_count += 1
            shard_rows += 1
            if row_count % 1000 == 0:
                print(f"downloaded {row_count} rows...", file=sys.stderr)
        print(f"  {parquet_file}: {shard_rows} rows", file=sys.stderr)

    manifest: dict[str, Any] = {
        "dataset_id": args.dataset_id,
        "revision": revision,
        "split": split,
        "mode": args.mode,
        "parquet_files": parquet_files,
        "all_train_shards": args.all_train_shards,
        "train_shards": args.train_shards if args.all_train_shards else None,
        "license": cfg.get("license"),
        "license_note": cfg.get("license_note"),
        "uri": cfg.get("uri"),
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "row_count": row_count,
        "raw_path": str(raw_path),
        "max_rows_per_shard": args.max_rows,
    }
    write_json(manifest_path, manifest)
    print(f"wrote {row_count} rows -> {raw_path}")
    print(f"manifest -> {manifest_path}")


if __name__ == "__main__":
    main()
