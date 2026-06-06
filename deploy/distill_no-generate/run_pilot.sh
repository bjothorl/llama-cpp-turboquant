#!/usr/bin/env bash
# Pilot: download KodCode -> normalize -> filter -> verify subset.
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
MAX_ROWS="${MAX_ROWS:-1000}"
SAMPLE_SIZE="${SAMPLE_SIZE:-50}"
SLUG="${DATASET_ID//\//__}"

CACHE="${CACHE:-$TRACK/phase1/cache/$SLUG}"
RAW_NORM="${RAW_NORM:-$TRACK/phase1/outputs/${SLUG}.jsonl}"
FILTERED="${FILTERED:-$TRACK/phase1/outputs/${SLUG}.filtered.jsonl}"
VERIFIED="${VERIFIED:-$TRACK/phase2/outputs/${SLUG}.pilot.verified.jsonl}"

echo "==> Download ($MAX_ROWS rows)"
"$PYTHON" "$TRACK/phase1/download.py" "$DATASET_ID" --out "$CACHE" --max-rows "$MAX_ROWS" --overwrite

echo "==> Normalize"
"$PYTHON" "$TRACK/phase1/normalize.py" "$DATASET_ID" --cache "$CACHE" --out "$RAW_NORM"

echo "==> Filter"
"$PYTHON" "$TRACK/phase1/filter.py" --input "$RAW_NORM" --output "$FILTERED"

echo "==> Verify subset ($SAMPLE_SIZE rows)"
"$PYTHON" "$TRACK/phase2/verify_subset.py" \
  --input "$FILTERED" \
  --output "$VERIFIED" \
  --sample-size "$SAMPLE_SIZE"

echo "==> Export SFT"
"$PYTHON" "$TRACK/phase2/export_sft.py" \
  --input "$FILTERED" \
  --output "$TRACK/phase2/outputs/kodcode_pilot_sft.jsonl"

echo "Done."
echo "  filtered: $FILTERED"
echo "  verified: $VERIFIED"
echo "  sft:      $TRACK/phase2/outputs/kodcode_pilot_sft.jsonl"
