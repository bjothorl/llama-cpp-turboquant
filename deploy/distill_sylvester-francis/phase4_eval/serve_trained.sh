#!/usr/bin/env bash
# Start llama-server on a locally-built GGUF (output of phase3_convert).
# Thin wrapper around deploy/distill/phase0/start_server.sh.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PHASE_DIR="$ROOT/deploy/distill_sylvester-francis/phase4_eval"

MODEL_PATH=""
RUN_DIR="${RUN_DIR:-$PHASE_DIR/runs/trained}"
PORT="${PORT:-8080}"
DRAFT="${DRAFT:-2}"

usage() {
  cat <<EOF
Usage: $0 --model PATH [--run-dir DIR] [--port PORT] [--draft N]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model) MODEL_PATH="$2"; shift 2 ;;
    --run-dir) RUN_DIR="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --draft) DRAFT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$MODEL_PATH" ]]; then
  usage >&2
  exit 2
fi
if [[ ! -f "$MODEL_PATH" ]]; then
  printf 'model file not found: %s\n' "$MODEL_PATH" >&2
  exit 1
fi

mkdir -p "$RUN_DIR"
printf '%s\n' "$MODEL_PATH" > "$RUN_DIR/MODEL_PATH.txt"

exec "$ROOT/deploy/distill/phase0/start_server.sh" \
  --model "$MODEL_PATH" \
  --run-dir "$RUN_DIR" \
  --port "$PORT" \
  --draft "$DRAFT"
