#!/usr/bin/env bash
# Full TypeScript verify-only pipeline: generate -> verify -> select passed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

GEN_ENV="${GEN_ENV:-deploy/distill_no-repair/phase1/generator.env}"
VER_ENV="${VER_ENV:-deploy/distill_no-repair/phase2/verifier.env}"

# Override via environment: PROMPTS_FILE, RAW_OUTPUT, VERIFIED_OUTPUT, SFT_OUTPUT, MAX_SAMPLES, CANDIDATES
PROMPTS_FILE="${PROMPTS_FILE:-deploy/distill_no-repair/phase1/prompts/typescript_tasks_30.jsonl}"
RAW_OUTPUT="${RAW_OUTPUT:-deploy/distill_no-repair/phase1/outputs/typescript_candidates_50x.jsonl}"
VERIFIED_OUTPUT="${VERIFIED_OUTPUT:-deploy/distill_no-repair/phase2/outputs/typescript_candidates_50x.verified.jsonl}"
SFT_OUTPUT="${SFT_OUTPUT:-deploy/distill_no-repair/phase2/outputs/solution_sft.jsonl}"
MAX_SAMPLES="${MAX_SAMPLES:-30}"
CANDIDATES="${CANDIDATES:-50}"

if [[ ! -f "$GEN_ENV" ]]; then
  cp deploy/distill_no-repair/phase1/generator.env.example "$GEN_ENV"
fi
if [[ ! -f "$VER_ENV" ]]; then
  cp deploy/distill_no-repair/phase2/verifier.env.example "$VER_ENV"
fi

rm -f "$RAW_OUTPUT"
echo "==> Generate ($MAX_SAMPLES tasks x $CANDIDATES candidates)"
python3 deploy/distill_no-repair/phase1/generate_samples.py \
  --env-file "$GEN_ENV" \
  --prompts "$PROMPTS_FILE" \
  --output "$RAW_OUTPUT" \
  --max-samples "$MAX_SAMPLES" \
  --candidates "$CANDIDATES"

echo "==> Verify"
python3 deploy/distill_no-repair/phase2/verify_samples.py \
  --env-file "$VER_ENV" \
  --input "$RAW_OUTPUT" \
  --output "$VERIFIED_OUTPUT" \
  --install-node-deps

echo "==> Select passing samples"
python3 deploy/distill_no-repair/phase2/select_passed.py \
  --input "$VERIFIED_OUTPUT" \
  --output "$SFT_OUTPUT" \
  --max-per-task 10

echo "==> Summary"
python3 deploy/distill_no-repair/phase1/analyze_pass_rates.py \
  --input "$VERIFIED_OUTPUT" \
  --manifest "${SFT_OUTPUT%.jsonl}.manifest.json"

echo "Done. SFT rows: $SFT_OUTPUT"
