#!/usr/bin/env bash
# Full KodCode run: all train shards -> normalize -> filter -> verify sample -> export SFT.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TRACK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON="${TRACK}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "missing venv at $TRACK/.venv — run: python3 -m venv $TRACK/.venv && $TRACK/.venv/bin/pip install -r $TRACK/requirements.txt"
  exit 1
fi

DATASET_ID="${DATASET_ID:-KodCode/KodCode-V1-SFT-4o}"
TRAIN_SHARDS="${TRAIN_SHARDS:-5}"
MAX_ROWS="${MAX_ROWS:-0}"          # 0 = all rows per shard
SAMPLE_SIZE="${SAMPLE_SIZE:-500}"  # harness sanity check only
SLUG="${DATASET_ID//\//__}"

CACHE="${CACHE:-$TRACK/phase1/cache/${SLUG}_full}"
RAW_NORM="${RAW_NORM:-$TRACK/phase1/outputs/${SLUG}.full.jsonl}"
FILTERED="${FILTERED:-$TRACK/phase1/outputs/${SLUG}.full.filtered.jsonl}"
VERIFIED="${VERIFIED:-$TRACK/phase2/outputs/${SLUG}.full.verified.jsonl}"
SFT_OUTPUT="${SFT_OUTPUT:-$TRACK/phase2/outputs/kodcode_full_sft.jsonl}"

echo "==> Download (all $TRAIN_SHARDS train shards, max-rows=$MAX_ROWS per shard)"
"$PYTHON" "$TRACK/phase1/download.py" "$DATASET_ID" \
  --out "$CACHE" \
  --all-train-shards \
  --train-shards "$TRAIN_SHARDS" \
  --max-rows "$MAX_ROWS" \
  --overwrite

echo "==> Normalize"
"$PYTHON" "$TRACK/phase1/normalize.py" "$DATASET_ID" --cache "$CACHE" --out "$RAW_NORM"

echo "==> Filter"
"$PYTHON" "$TRACK/phase1/filter.py" --input "$RAW_NORM" --output "$FILTERED"

echo "==> Verify subset ($SAMPLE_SIZE rows, optional harness check)"
"$PYTHON" "$TRACK/phase2/verify_subset.py" \
  --input "$FILTERED" \
  --output "$VERIFIED" \
  --sample-size "$SAMPLE_SIZE"

echo "==> Export SFT"
"$PYTHON" "$TRACK/phase2/export_sft.py" \
  --input "$FILTERED" \
  --output "$SFT_OUTPUT"

echo "Done."
echo "  filtered: $FILTERED"
echo "  verified: $VERIFIED"
echo "  sft:      $SFT_OUTPUT"
