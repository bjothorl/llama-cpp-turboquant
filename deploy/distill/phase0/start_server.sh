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

MODEL_HF="${MODEL_HF:-unsloth/Qwen3.5-9B-MTP-GGUF}"
MODEL_PATH="${MODEL_PATH:-}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
CTX_SIZE="${CTX_SIZE:-8192}"
N_GPU_LAYERS="${N_GPU_LAYERS:-99}"
SPEC_DRAFT_N_MAX="${SPEC_DRAFT_N_MAX:-2}"
REASONING="${REASONING:-on}"
REASONING_FORMAT="${REASONING_FORMAT:-deepseek}"
TEMP="${TEMP:-0.6}"
TOP_P="${TOP_P:-0.95}"
TOP_K="${TOP_K:-20}"
MIN_P="${MIN_P:-0.0}"
PRESENCE_PENALTY="${PRESENCE_PENALTY:-0.1}"
N_PREDICT="${N_PREDICT:-512}"
RUN_DIR="${RUN_DIR:-$PHASE_DIR/runs/$(date -u +%Y%m%dT%H%M%SZ)}"
READY_TIMEOUT="${READY_TIMEOUT:-300}"

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --run-dir DIR              Artifact directory
  --model-hf REPO[:QUANT]    Hugging Face GGUF repo
  --model PATH               Local GGUF file path
  --host HOST                Server host (default: $HOST)
  --port PORT                Server port (default: $PORT)
  --ctx-size N               Context size (default: $CTX_SIZE)
  --draft N                  --spec-draft-n-max value (default: $SPEC_DRAFT_N_MAX)
  --help                     Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir) RUN_DIR="$2"; shift 2 ;;
    --model-hf) MODEL_HF="$2"; MODEL_PATH=""; shift 2 ;;
    --model) MODEL_PATH="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --ctx-size) CTX_SIZE="$2"; shift 2 ;;
    --draft) SPEC_DRAFT_N_MAX="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

mkdir -p "$RUN_DIR"

curl_auth=()
if [[ -n "${LLAMA_API_KEY:-}" ]]; then
  curl_auth=(-H "Authorization: Bearer ${LLAMA_API_KEY}")
fi

if [[ -f "$RUN_DIR/server.pid" ]]; then
  old_pid="$(tr -d '[:space:]' < "$RUN_DIR/server.pid")"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    printf 'Server already appears to be running for %s with pid %s\n' "$RUN_DIR" "$old_pid" >&2
    exit 1
  fi
fi

cmd=("$ROOT/build/bin/llama-server")
if [[ -n "$MODEL_PATH" ]]; then
  cmd+=("-m" "$MODEL_PATH")
else
  cmd+=("-hf" "$MODEL_HF")
fi
cmd+=(
  "--reasoning" "$REASONING"
  "--reasoning-format" "$REASONING_FORMAT"
  "--temp" "$TEMP"
  "--top-p" "$TOP_P"
  "--top-k" "$TOP_K"
  "--min-p" "$MIN_P"
  "--presence-penalty" "$PRESENCE_PENALTY"
  "--spec-type" "draft-mtp"
  "--spec-draft-n-max" "$SPEC_DRAFT_N_MAX"
  "--host" "$HOST"
  "--port" "$PORT"
  "-ngl" "$N_GPU_LAYERS"
  "-fa" "on"
  "-c" "$CTX_SIZE"
  "-np" "1"
  "-n" "$N_PREDICT"
)

{
  printf 'cd %q\n' "$ROOT"
  printf '%q ' "${cmd[@]}"
  printf '\n'
} > "$RUN_DIR/server_command.txt"

(
  cd "$ROOT"
  exec "${cmd[@]}"
) > "$RUN_DIR/server.log" 2>&1 &
pid="$!"
printf '%s\n' "$pid" > "$RUN_DIR/server.pid"

printf 'Started llama-server pid=%s\n' "$pid"
printf 'RUN_DIR=%s\n' "$RUN_DIR"

deadline=$((SECONDS + READY_TIMEOUT))
ready=0
while (( SECONDS < deadline )); do
  if ! kill -0 "$pid" 2>/dev/null; then
    printf 'server exited before becoming ready\n' >&2
    break
  fi

  if curl -fsS "${curl_auth[@]}" "http://$HOST:$PORT/health" >/dev/null 2>&1 || \
     curl -fsS "${curl_auth[@]}" "http://$HOST:$PORT/v1/models" >/dev/null 2>&1; then
    ready=1
    break
  fi

  if grep -Eiq 'unsupported|out of memory|oom|address already in use|nextn_predict_layers.*0|failed to load|error loading model' "$RUN_DIR/server.log"; then
    printf 'server log contains an early failure pattern\n' >&2
    break
  fi

  sleep 2
done

if [[ "$ready" == "1" ]]; then
  printf 'server_ready=true\n'
  exit 0
fi

printf 'server_ready=false\n' >&2
printf 'Last server log lines:\n' >&2
tail -n 80 "$RUN_DIR/server.log" >&2 || true
exit 1
