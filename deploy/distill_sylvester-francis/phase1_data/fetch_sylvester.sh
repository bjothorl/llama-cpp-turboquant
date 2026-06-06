#!/usr/bin/env bash
# Clone sylvester-francis/slm-typescript-model and stage its processed JSONL
# into deploy/distill_sylvester-francis/data/.
#
# By default skips the GitHub scraping step (`slm.py collect`) because that
# requires GITHUB_TOKEN and can take hours. Pass --collect to opt in.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PHASE_DIR="$ROOT/deploy/distill_sylvester-francis"

if [[ -f "$PHASE_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PHASE_DIR/.env"
  set +a
fi

SYLVESTER_REPO="${SYLVESTER_REPO:-$HOME/slm-typescript-model}"
DO_COLLECT=0
DO_PREPROCESS=1

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --repo PATH         Clone destination (default: $SYLVESTER_REPO)
  --collect           Also run slm.py collect (requires GITHUB_TOKEN, slow)
  --no-preprocess     Skip slm.py preprocess (use already-processed JSONL)
  -h, --help          Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) SYLVESTER_REPO="$2"; shift 2 ;;
    --collect) DO_COLLECT=1; shift ;;
    --no-preprocess) DO_PREPROCESS=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ ! -d "$SYLVESTER_REPO/.git" ]]; then
  printf 'Cloning sylvester-francis/slm-typescript-model into %s\n' "$SYLVESTER_REPO"
  git clone https://github.com/sylvester-francis/slm-typescript-model.git "$SYLVESTER_REPO"
else
  printf 'Existing clone at %s — running git pull\n' "$SYLVESTER_REPO"
  git -C "$SYLVESTER_REPO" pull --ff-only || true
fi

if (( DO_COLLECT )); then
  : "${GITHUB_TOKEN:?GITHUB_TOKEN is required for --collect}"
  printf 'Running slm.py collect (this can take a long time)\n'
  (
    cd "$SYLVESTER_REPO"
    GITHUB_TOKEN="$GITHUB_TOKEN" python3 slm.py collect
  )
fi

if (( DO_PREPROCESS )); then
  if [[ ! -d "$SYLVESTER_REPO/data/raw" ]]; then
    printf 'warning: %s/data/raw does not exist — preprocess will produce nothing\n' "$SYLVESTER_REPO" >&2
    printf '  Re-run with --collect to scrape, or copy raw data manually.\n' >&2
  else
    printf 'Running slm.py preprocess\n'
    (
      cd "$SYLVESTER_REPO"
      python3 slm.py preprocess
    )
  fi
fi

dest="$PHASE_DIR/data"
mkdir -p "$dest"

linked=0
for name in train_small.jsonl train_ultra.jsonl train_medium.jsonl train.jsonl validation.jsonl; do
  src="$SYLVESTER_REPO/data/processed/$name"
  if [[ -f "$src" ]]; then
    ln -sf "$src" "$dest/$name"
    printf '  linked %s -> %s\n' "$dest/$name" "$src"
    linked=$((linked + 1))
  fi
done

if (( linked == 0 )); then
  printf '\nNo processed JSONL files found in %s/data/processed/.\n' "$SYLVESTER_REPO" >&2
  printf 'Re-run with --collect (and GITHUB_TOKEN) or supply your own data.\n' >&2
  exit 1
fi

printf '\nStaged %d file(s) into %s\n' "$linked" "$dest"
printf 'Next: python3 %s/phase1_data/inspect_data.py --input %s/train_small.jsonl\n' "$PHASE_DIR" "$dest"
