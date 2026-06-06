#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PHASE_DIR="$ROOT/deploy/distill/phase0"
RUN_DIR=""

usage() {
  printf 'Usage: %s --run-dir DIR\n' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir)
      RUN_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$RUN_DIR" ]]; then
  usage >&2
  exit 2
fi

pid_file="$RUN_DIR/server.pid"
if [[ ! -f "$pid_file" ]]; then
  printf 'No server.pid found in %s\n' "$RUN_DIR"
  exit 0
fi

pid="$(tr -d '[:space:]' < "$pid_file")"
if [[ -z "$pid" ]]; then
  printf 'server.pid is empty\n'
  exit 0
fi

if ! kill -0 "$pid" 2>/dev/null; then
  printf 'Server pid %s is not running\n' "$pid"
  exit 0
fi

kill "$pid"
for _ in $(seq 1 30); do
  if ! kill -0 "$pid" 2>/dev/null; then
    printf 'Stopped server pid %s\n' "$pid"
    exit 0
  fi
  sleep 1
done

printf 'Server pid %s did not stop after SIGTERM; sending SIGKILL\n' "$pid" >&2
kill -9 "$pid" 2>/dev/null || true
