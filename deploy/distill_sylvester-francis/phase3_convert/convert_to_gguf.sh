#!/usr/bin/env bash
# Convert a merged HF safetensors checkpoint to GGUF, preserving MTP, then
# optionally quantize.
#
# Note: do NOT pass --mtp to convert_hf_to_gguf.py here. The default code
# path for Qwen3_5TextModel / Qwen3_5MoeTextModel already emits NextN
# tensors and nextn_predict_layers; --mtp produces a draft-only submodel,
# which is not what we want for llama-server --spec-type draft-mtp.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PHASE_DIR="$ROOT/deploy/distill_sylvester-francis"

if [[ -f "$PHASE_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PHASE_DIR/.env"
  set +a
fi

SRC=""
OUT=""
QUANT="Q4_K_M"          # llama-quantize target
INTERMEDIATE_TYPE="f16"  # convert_hf_to_gguf.py --outtype
SKIP_QUANTIZE=0

usage() {
  cat <<EOF
Usage: $0 --src DIR --out FILE [--quant TYPE] [--intermediate TYPE] [--no-quantize]

Required:
  --src DIR              Merged HF checkpoint (output of merge_adapter.py)
  --out FILE             Final GGUF path (e.g. models/qwen35-9b-ts.Q4_K_M.gguf)

Optional:
  --quant TYPE           llama-quantize target (default: $QUANT, e.g. Q4_K_M, Q5_K_M, Q8_0)
  --intermediate TYPE    convert_hf_to_gguf.py --outtype (default: $INTERMEDIATE_TYPE)
  --no-quantize          Skip the llama-quantize step; --out becomes the intermediate file
  -h, --help             Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --src) SRC="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --quant) QUANT="$2"; shift 2 ;;
    --intermediate) INTERMEDIATE_TYPE="$2"; shift 2 ;;
    --no-quantize) SKIP_QUANTIZE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$SRC" || -z "$OUT" ]]; then
  usage >&2
  exit 2
fi

if [[ ! -d "$SRC" ]]; then
  printf 'source directory not found: %s\n' "$SRC" >&2
  exit 1
fi

CONVERT="$ROOT/convert_hf_to_gguf.py"
QUANTIZE="$ROOT/build/bin/llama-quantize"

if [[ ! -f "$CONVERT" ]]; then
  printf 'convert script not found: %s\n' "$CONVERT" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"

if (( SKIP_QUANTIZE )); then
  INTERMEDIATE="$OUT"
else
  INTERMEDIATE="${OUT%.gguf}.${INTERMEDIATE_TYPE}.gguf"
fi

printf '== convert (preserving MTP) ==\n'
printf '  src=%s\n' "$SRC"
printf '  intermediate=%s outtype=%s\n' "$INTERMEDIATE" "$INTERMEDIATE_TYPE"
python3 "$CONVERT" \
  --outfile "$INTERMEDIATE" \
  --outtype "$INTERMEDIATE_TYPE" \
  "$SRC"

if (( SKIP_QUANTIZE )); then
  printf '== done (no quantize requested) ==\n'
  printf '  output=%s\n' "$INTERMEDIATE"
  exit 0
fi

if [[ ! -x "$QUANTIZE" ]]; then
  printf 'llama-quantize not found at %s\n' "$QUANTIZE" >&2
  printf '  Build llama.cpp first (cmake --build build --target llama-quantize)\n' >&2
  exit 1
fi

printf '== quantize ==\n'
printf '  in=%s out=%s type=%s\n' "$INTERMEDIATE" "$OUT" "$QUANT"
"$QUANTIZE" "$INTERMEDIATE" "$OUT" "$QUANT"

printf '== done ==\n'
printf '  output=%s\n' "$OUT"
printf '\nSanity check (MTP metadata should be present):\n'
printf '  %s/build/bin/llama-gguf %s | grep -i nextn\n' "$ROOT" "$OUT"
