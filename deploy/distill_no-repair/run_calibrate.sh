#!/usr/bin/env bash
# Generate ~50 TS samples, verify, and analyze pass rates before a full 50x run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

GEN_ENV="${GEN_ENV:-deploy/distill_no-repair/phase1/generator.env}"
VER_ENV="${VER_ENV:-deploy/distill_no-repair/phase2/verifier.env}"

RAW="deploy/distill_no-repair/phase1/outputs/calibrate_10x5.jsonl"
VERIFIED="deploy/distill_no-repair/phase2/outputs/calibrate_10x5.verified.jsonl"
ANALYSIS="deploy/distill_no-repair/phase2/outputs/calibrate_10x5.analysis.txt"

if [[ ! -f "$GEN_ENV" ]]; then
  cp deploy/distill_no-repair/phase1/generator.env.example "$GEN_ENV"
  echo "Created $GEN_ENV — review paths before running."
fi
if [[ ! -f "$VER_ENV" ]]; then
  cp deploy/distill_no-repair/phase2/verifier.env.example "$VER_ENV"
  echo "Created $VER_ENV — set INSTALL_NODE_DEPS=true for Vitest/tsc."
fi

rm -f "$RAW"
echo "==> Generate calibration corpus (10 tasks x 5 candidates)"
python3 deploy/distill_no-repair/phase1/generate_samples.py \
  --env-file "$GEN_ENV" \
  --prompts deploy/distill_no-repair/phase1/prompts/typescript_tasks_calibrate.jsonl \
  --output "$RAW" \
  --max-samples 10 \
  --candidates 5

echo "==> Verify"
python3 deploy/distill_no-repair/phase2/verify_samples.py \
  --env-file "$VER_ENV" \
  --input "$RAW" \
  --output "$VERIFIED" \
  --install-node-deps

echo "==> Analyze"
python3 deploy/distill_no-repair/phase1/analyze_pass_rates.py \
  --input "$VERIFIED" \
  --output "$ANALYSIS"

echo "Done. Review $ANALYSIS before run_pipeline.sh"
