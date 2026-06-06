#!/usr/bin/env python3
"""Generate Phase 0 baseline reports from run artifacts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, help="Run directory or sweep directory")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def candidate_dirs(root: Path) -> list[Path]:
    dirs: list[Path] = []
    if any((root / name).exists() for name in ("preflight.json", "smoke_summary.json", "server.log")):
        dirs.append(root)
    for child in sorted(root.iterdir() if root.exists() else []):
        if child.is_dir() and any((child / name).exists() for name in ("preflight.json", "smoke_summary.json", "server.log")):
            dirs.append(child)
    return dirs


def parse_acceptance(log_path: Path) -> str | float:
    if not log_path.exists():
        return "not_reported"
    text = log_path.read_text(errors="replace")
    patterns = [
        r"acceptance(?: rate)?[:=]\s*([0-9]+(?:\.[0-9]+)?)%?",
        r"accepted[^0-9]+([0-9]+)\s*/\s*([0-9]+)",
        r"draft[^.\n]*accept[^0-9]+([0-9]+(?:\.[0-9]+)?)%?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        if len(match.groups()) == 2:
            accepted = float(match.group(1))
            total = float(match.group(2))
            return accepted / total if total else "not_reported"
        value = float(match.group(1))
        return value / 100.0 if value > 1.0 else value
    return "not_reported"


def extract_model(command: str | None) -> str | None:
    if not command:
        return None
    tokens = command.split()
    for flag in ("-hf", "--hf-repo", "-m", "--model"):
        if flag in tokens:
            idx = tokens.index(flag)
            if idx + 1 < len(tokens):
                return tokens[idx + 1].strip("'\"")
    return None


def extract_flag(command: str | None, flag: str) -> str | None:
    if not command:
        return None
    tokens = command.split()
    if flag in tokens:
        idx = tokens.index(flag)
        if idx + 1 < len(tokens):
            return tokens[idx + 1].strip("'\"")
    return None


def gpu_summary(preflight: dict[str, Any] | None) -> str | None:
    if not preflight:
        return None
    gpu = preflight.get("gpu") or {}
    gpus = gpu.get("gpus") or []
    if not gpus:
        return gpu.get("reason") or "none"
    return "; ".join(
        f"{item.get('name')} {item.get('memory_used_mib')}/{item.get('memory_total_mib')} MiB"
        for item in gpus
    )


def collect_run(run_dir: Path) -> dict[str, Any]:
    preflight = read_json(run_dir / "preflight.json")
    smoke = read_json(run_dir / "smoke_summary.json")
    status = read_json(run_dir / "run_status.json")
    command = (run_dir / "server_command.txt").read_text(errors="replace").strip() if (run_dir / "server_command.txt").exists() else None
    draft = None
    if status:
        draft = status.get("draft")
    draft = draft or extract_flag(command, "--spec-draft-n-max")
    model = extract_model(command)
    ctx = extract_flag(command, "-c") or extract_flag(command, "--ctx-size")
    return {
        "run_dir": str(run_dir),
        "model": model,
        "context": ctx,
        "draft": draft,
        "command": command,
        "git_sha": (preflight or {}).get("git", {}).get("sha"),
        "git_dirty": (preflight or {}).get("git", {}).get("dirty"),
        "gpu": gpu_summary(preflight),
        "smoke": smoke,
        "status": status,
        "acceptance": parse_acceptance(run_dir / "server.log"),
    }


def write_markdown(root: Path, runs: list[dict[str, Any]]) -> None:
    lines = [
        "# Phase 0 Baseline",
        "",
        f"Run root: `{root}`",
        "",
        "| Model | Context | Draft | Acceptance | Avg tok/s | OK/Total | GPU | Notes |",
        "|-------|---------|-------|------------|-----------|----------|-----|-------|",
    ]
    for run in runs:
        smoke = run.get("smoke") or {}
        ok = smoke.get("ok")
        total = smoke.get("total")
        ok_total = f"{ok}/{total}" if ok is not None and total is not None else "not_run"
        notes = []
        status = run.get("status") or {}
        if status.get("start_status") not in (None, 0):
            notes.append(f"start={status.get('start_status')}")
        if status.get("smoke_status") not in (None, 0):
            notes.append(f"smoke={status.get('smoke_status')}")
        if smoke.get("repetition_warnings"):
            notes.append(f"repeat={smoke.get('repetition_warnings')}")
        lines.append(
            "| {model} | {ctx} | {draft} | {acceptance} | {tps} | {ok_total} | {gpu} | {notes} |".format(
                model=run.get("model") or "unknown",
                ctx=run.get("context") or "unknown",
                draft=run.get("draft") or "unknown",
                acceptance=run.get("acceptance"),
                tps=smoke.get("avg_tokens_per_second"),
                ok_total=ok_total,
                gpu=run.get("gpu") or "unknown",
                notes=", ".join(notes) if notes else "-",
            )
        )
    lines.extend(["", "## Commands", ""])
    for run in runs:
        lines.extend([
            f"### `{Path(run['run_dir']).name}`",
            "",
            "```bash",
            run.get("command") or "not recorded",
            "```",
            "",
        ])
    (root / "baseline.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    root = Path(parse_args().run_root)
    dirs = candidate_dirs(root)
    runs = [collect_run(run_dir) for run_dir in dirs]
    payload = {"run_root": str(root), "runs": runs}
    root.mkdir(parents=True, exist_ok=True)
    (root / "baseline.json").write_text(json.dumps(payload, indent=2) + "\n")
    write_markdown(root, runs)
    print(f"Wrote {root / 'baseline.md'}")
    print(f"Wrote {root / 'baseline.json'}")


if __name__ == "__main__":
    main()
