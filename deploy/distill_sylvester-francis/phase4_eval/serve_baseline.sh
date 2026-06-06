#!/usr/bin/env bash
# Start llama-server on the untrained unsloth Qwen3.5-9B-MTP-GGUF baseline.
# Thin wrapper around deploy/distill/phase0/start_server.sh.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PHASE_DIR="$ROOT/deploy/distill_sylvester-francis/phase4_eval"

MODEL_HF="${MODEL_HF:-unsloth/Qwen3.5-9B-MTP-GGUF:UD-Q4_K_XL}"
RUN_DIR="${RUN_DIR:-$PHASE_DIR/runs/baseline}"
PORT="${PORT:-8080}"
DRAFT="${DRAFT:-2}"

usage() {
  cat <<EOF
Usage: $0 [--model-hf REPO[:QUANT]] [--run-dir DIR] [--port PORT] [--draft N]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model-hf) MODEL_HF="$2"; shift 2 ;;
    --run-dir) RUN_DIR="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --draft) DRAFT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

mkdir -p "$RUN_DIR"
printf '%s\n' "$MODEL_HF" > "$RUN_DIR/MODEL_HF.txt"

exec "$ROOT/deploy/distill/phase0/start_server.sh" \
  --model-hf "$MODEL_HF" \
  --run-dir "$RUN_DIR" \
  --port "$PORT" \
  --draft "$DRAFT"
