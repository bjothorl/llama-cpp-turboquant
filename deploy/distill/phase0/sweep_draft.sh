#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PHASE_DIR="$ROOT/deploy/distill/phase0"

if [[ -f "$PHASE_DIR/models.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PHASE_DIR/models.env"
  set +a
fi

DRAFTS="${DRAFTS:-1,2,3}"
PROMPTS="${PROMPTS:-$PHASE_DIR/prompts/smoke-10.jsonl}"
SWEEP_DIR="${SWEEP_DIR:-$PHASE_DIR/runs/sweep-$(date -u +%Y%m%dT%H%M%SZ)}"
MODEL_HF="${MODEL_HF:-unsloth/Qwen3.5-9B-MTP-GGUF}"
MODEL_PATH="${MODEL_PATH:-}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
CTX_SIZE="${CTX_SIZE:-8192}"

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --drafts LIST       Comma-separated draft lengths (default: $DRAFTS)
  --prompts FILE      JSONL prompt file (default: $PROMPTS)
  --sweep-dir DIR     Sweep output directory
  --model-hf REPO     Hugging Face model repo
  --model PATH        Local GGUF model path
  --host HOST         Server host
  --port PORT         Server port
  --ctx-size N        Context size
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --drafts) DRAFTS="$2"; shift 2 ;;
    --prompts) PROMPTS="$2"; shift 2 ;;
    --sweep-dir) SWEEP_DIR="$2"; shift 2 ;;
    --model-hf) MODEL_HF="$2"; MODEL_PATH=""; shift 2 ;;
    --model) MODEL_PATH="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --ctx-size) CTX_SIZE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

mkdir -p "$SWEEP_DIR"
printf 'SWEEP_DIR=%s\n' "$SWEEP_DIR"

IFS=',' read -r -a draft_values <<< "$DRAFTS"

for draft in "${draft_values[@]}"; do
  draft="$(printf '%s' "$draft" | tr -d '[:space:]')"
  [[ -n "$draft" ]] || continue
  run_dir="$SWEEP_DIR/draft-$draft"
  mkdir -p "$run_dir"

  printf '\n== draft %s ==\n' "$draft"
  "$PHASE_DIR/preflight.sh" --host "$HOST" --port "$PORT" --run-dir "$run_dir"

  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi > "$run_dir/nvidia-smi-before.txt" || true
  fi

  start_args=(
    --run-dir "$run_dir"
    --host "$HOST"
    --port "$PORT"
    --ctx-size "$CTX_SIZE"
    --draft "$draft"
  )
  if [[ -n "$MODEL_PATH" ]]; then
    start_args+=(--model "$MODEL_PATH")
  else
    start_args+=(--model-hf "$MODEL_HF")
  fi

  set +e
  "$PHASE_DIR/start_server.sh" "${start_args[@]}"
  start_status=$?
  if [[ "$start_status" -eq 0 ]]; then
    python3 "$PHASE_DIR/run_smoke.py" \
      --run-dir "$run_dir" \
      --prompts "$PROMPTS" \
      --host "$HOST" \
      --port "$PORT"
    smoke_status=$?
  else
    smoke_status=1
  fi
  "$PHASE_DIR/stop_server.sh" --run-dir "$run_dir"
  set -e

  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi > "$run_dir/nvidia-smi-after.txt" || true
  fi

  python3 - "$run_dir" "$draft" "$start_status" "$smoke_status" <<'PY'
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
payload = {
    "draft": sys.argv[2],
    "start_status": int(sys.argv[3]),
    "smoke_status": int(sys.argv[4]),
}
(run_dir / "run_status.json").write_text(json.dumps(payload, indent=2) + "\n")
PY

  if [[ "$start_status" -ne 0 || "$smoke_status" -ne 0 ]]; then
    printf 'draft %s completed with errors: start=%s smoke=%s\n' "$draft" "$start_status" "$smoke_status" >&2
  fi
done

python3 "$PHASE_DIR/report.py" --run-root "$SWEEP_DIR"
