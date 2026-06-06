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

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
RUN_DIR="${RUN_DIR:-$PHASE_DIR/runs/$(date -u +%Y%m%dT%H%M%SZ)}"

usage() {
  printf 'Usage: %s [--host HOST] [--port PORT] [--run-dir DIR]\n' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
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

mkdir -p "$RUN_DIR"

export ROOT PHASE_DIR HOST PORT RUN_DIR
python3 - <<'PY'
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

root = Path(os.environ["ROOT"])
run_dir = Path(os.environ["RUN_DIR"])
host = os.environ["HOST"]
port = int(os.environ["PORT"])
binary = root / "build" / "bin" / "llama-server"


def run(args):
    try:
        return subprocess.run(
            args,
            cwd=root,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        return exc


def git_status_short():
    result = run(["git", "status", "--short"])
    if isinstance(result, FileNotFoundError):
        return [f"git unavailable: {result}"]
    if result.returncode != 0:
        return [result.stderr.strip()]
    return [line for line in result.stdout.splitlines() if line.strip()]


def git_sha():
    result = run(["git", "rev-parse", "HEAD"])
    if isinstance(result, FileNotFoundError) or result.returncode != 0:
        return None
    return result.stdout.strip()


def check_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def gpu_info():
    if shutil.which("nvidia-smi") is None:
        return {"available": False, "reason": "nvidia-smi not found", "gpus": []}
    result = run([
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.used",
        "--format=csv,noheader,nounits",
    ])
    if isinstance(result, FileNotFoundError) or result.returncode != 0:
        return {
            "available": False,
            "reason": getattr(result, "stderr", "nvidia-smi failed").strip(),
            "gpus": [],
        }
    gpus = []
    for idx, line in enumerate(result.stdout.splitlines()):
        parts = [part.strip() for part in line.split(",")]
        if len(parts) == 3:
            name, total, used = parts
            gpus.append({
                "index": idx,
                "name": name,
                "memory_total_mib": int(total),
                "memory_used_mib": int(used),
            })
    return {"available": True, "reason": None, "gpus": gpus}


port_in_use = check_port()
payload = {
    "root": str(root),
    "run_dir": str(run_dir),
    "host": host,
    "port": port,
    "binary": {
        "path": str(binary),
        "exists": binary.exists(),
        "executable": os.access(binary, os.X_OK),
    },
    "git": {
        "sha": git_sha(),
        "status_short": git_status_short(),
        "dirty": bool(git_status_short()),
    },
    "tools": {
        "python3": shutil.which("python3"),
        "curl": shutil.which("curl"),
        "nvidia_smi": shutil.which("nvidia-smi"),
    },
    "auth": {
        "llama_api_key_configured": bool(os.environ.get("LLAMA_API_KEY")),
    },
    "gpu": gpu_info(),
    "port_in_use": port_in_use,
}

(run_dir / "preflight.json").write_text(json.dumps(payload, indent=2) + "\n")

print(f"RUN_DIR={run_dir}")
print(f"binary={payload['binary']['path']} exists={payload['binary']['exists']} executable={payload['binary']['executable']}")
print(f"git_sha={payload['git']['sha']}")
print(f"git_dirty={payload['git']['dirty']}")
print(f"gpu_available={payload['gpu']['available']}")
print(f"llama_api_key_configured={payload['auth']['llama_api_key_configured']}")
print(f"port={host}:{port} in_use={port_in_use}")

if not payload["binary"]["exists"] or not payload["binary"]["executable"]:
    print("preflight failed: build/bin/llama-server is missing or not executable", file=sys.stderr)
    sys.exit(1)
if shutil.which("curl") is None:
    print("preflight failed: curl is required", file=sys.stderr)
    sys.exit(1)
if port_in_use:
    print("preflight failed: requested port is already in use", file=sys.stderr)
    sys.exit(1)
PY
