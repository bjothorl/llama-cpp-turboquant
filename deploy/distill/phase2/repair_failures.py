#!/usr/bin/env python3
"""Repair failed Phase 2 samples using deterministic verifier feedback."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PHASE1_DIR = Path(__file__).resolve().parents[1] / "phase1"
sys.path.insert(0, str(PHASE1_DIR))

from extract_sample import parse_response  # noqa: E402


DEFAULT_ENV_FILE = Path(__file__).resolve().parent / "verifier.env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--input", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key-env", default="LLAMA_API_KEY")
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument("--include-unverified", action="store_true", help="Also repair unverified samples")
    parser.add_argument("--offset", type=int, default=None, help="Skip this many repairable samples before repairing")
    parser.add_argument("--max-repairs", type=int, default=None, help="Repair at most this many samples")
    parser.add_argument("--ids-file", default=None, help="Optional newline-delimited sample IDs to repair")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise SystemExit(f"{path}:{line_no}: expected KEY=VALUE")
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def env_value(args: argparse.Namespace, attr: str, env_name: str, default: str) -> str:
    value = getattr(args, attr)
    if value is not None:
        return str(value)
    return os.environ.get(env_name, default)


def env_float(args: argparse.Namespace, attr: str, env_name: str, default: float) -> float:
    value = getattr(args, attr)
    if value is not None:
        return float(value)
    return float(os.environ.get(env_name, default))


def env_int(args: argparse.Namespace, attr: str, env_name: str, default: int) -> int:
    value = getattr(args, attr)
    if value is not None:
        return int(value)
    return int(os.environ.get(env_name, default))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return rows


def load_ids(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    ids = {
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    return ids


def post_json(url: str, payload: dict[str, Any], api_key: str | None, timeout: float) -> tuple[int, dict[str, Any] | None, str | None]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(body), None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return exc.code, parsed, body
    except Exception as exc:  # noqa: BLE001 - diagnostic tool
        return 0, None, str(exc)


def truncate(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]..."


def failure_summary(sample: dict[str, Any]) -> str:
    phase2 = sample.get("verification", {}).get("phase2", {})
    blocks: list[str] = []
    for check in phase2.get("checks", []):
        if check.get("skipped"):
            continue
        if check.get("ok"):
            continue
        blocks.append(
            "\n".join([
                f"CHECK: {check.get('name')}",
                f"COMMAND: {' '.join(check.get('command') or [])}",
                f"STDOUT:\n{truncate(check.get('stdout') or '', 3000)}",
                f"STDERR:\n{truncate(check.get('stderr') or '', 6000)}",
            ])
        )
    return "\n\n---\n\n".join(blocks) or "No failing verifier output was recorded."


def build_repair_prompt(sample: dict[str, Any]) -> str:
    return f"""You are repairing a generated coding-training sample after automated verification failed.

Classify the failure and repair only what is necessary.

Allowed failure_cause values:
- bad_solution: tests reflect the task and the solution is wrong
- bad_tests: solution reflects the task and tests are wrong or overreach
- underspecified_task: original task lacks enough detail to decide
- harness_issue: verifier/test runner setup is the problem

Allowed repair_target values:
- solution
- tests
- none

Return exactly one JSON object with this shape:
{{
  "failure_cause": "bad_solution|bad_tests|underspecified_task|harness_issue",
  "repair_target": "solution|tests|none",
  "explanation": "brief reason, 240 characters or fewer",
  "code": "replacement solution code if repair_target is solution, otherwise empty string",
  "tests": "replacement test code if repair_target is tests, otherwise empty string"
}}

Rules:
- If repair_target is "solution", code must be non-empty and tests must be "".
- If repair_target is "tests", tests must be non-empty and code must be "".
- If the verifier/test runner setup is the problem, use failure_cause "harness_issue", repair_target "none", code "", tests "".
- If the task is underspecified, use failure_cause "underspecified_task", repair_target "none", code "", tests "".
- Tests should verify task-visible behavior. Avoid asserting exact framework or library internals, such as private error codes, unless the original task requires them.
- If generated tests use a framework or import style that is not available in the verifier, classify as "bad_tests" and rewrite tests for the available runner.
- If JavaScript code is not importable by its tests, classify as "bad_solution" and export the requested implementation.
- Keep explanation concise. Do not reason inside the JSON.

Do not include markdown fences. Do not change the original task.

ORIGINAL TASK:
{sample.get('prompt', '')}

LANGUAGE:
{sample.get('language', '')}

CURRENT SOLUTION:
{sample.get('code', '')}

CURRENT TESTS:
{sample.get('tests', '')}

VERIFIER FAILURE:
{failure_summary(sample)}
"""


def completion_payload(model: str, prompt: str, max_tokens: int, temperature: float, top_p: float) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You repair coding dataset samples. Return strict JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "chat_template_kwargs": {"enable_thinking": False},
        "reasoning_format": "deepseek",
        "response_format": {"type": "json_object"},
    }


def extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def repair_sample(
    sample: dict[str, Any],
    url: str,
    model: str,
    api_key: str | None,
    timeout: float,
    max_tokens: int,
    temperature: float,
    top_p: float,
) -> dict[str, Any]:
    prompt = build_repair_prompt(sample)
    payload = completion_payload(model, prompt, max_tokens, temperature, top_p)
    started = time.monotonic()
    status, response, error = post_json(url, payload, api_key, timeout)
    latency = time.monotonic() - started
    parsed_response = parse_response(response, sample.get("language"))
    content = parsed_response["content"]
    repair = extract_json_object(content) or {}

    repaired = dict(sample)
    attempts = list(sample.get("meta", {}).get("repair_attempts", []))
    original = {
        "code": sample.get("code", ""),
        "tests": sample.get("tests", ""),
        "phase2": sample.get("verification", {}).get("phase2"),
    }
    attempts.append({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "http_status": status,
        "latency_s": latency,
        "error": error,
        "request_model": model,
        "failure_summary": failure_summary(sample),
        "original": original,
        "raw": response,
        "parsed": repair,
    })
    repaired["meta"] = {**(sample.get("meta") or {}), "repair_attempts": attempts}

    target = repair.get("repair_target")
    if target == "solution" and isinstance(repair.get("code"), str) and repair["code"].strip():
        repaired["code"] = repair["code"].strip()
    elif target == "tests" and isinstance(repair.get("tests"), str) and repair["tests"].strip():
        repaired["tests"] = repair["tests"].strip()

    if attempts:
        attempts[-1]["result"] = {
            "code": repaired.get("code", ""),
            "tests": repaired.get("tests", ""),
        }

    parse_ok = bool(repair)
    repaired["verification"] = {
        **(sample.get("verification") or {}),
        "repair": {
            "failure_cause": repair.get("failure_cause") if parse_ok else "parse_error",
            "repair_target": target,
            "explanation": repair.get("explanation") if parse_ok else "teacher did not return parseable repair JSON",
            "applied": repaired.get("code") != sample.get("code") or repaired.get("tests") != sample.get("tests"),
            "parse_ok": parse_ok,
        },
    }
    return repaired


def should_repair(sample: dict[str, Any], include_unverified: bool) -> bool:
    phase2 = sample.get("verification", {}).get("phase2", {})
    status = phase2.get("status")
    return status == "failed" or (include_unverified and status == "unverified")


def main() -> None:
    args = parse_args()
    load_env_file(Path(args.env_file))
    input_path = Path(env_value(args, "input", "REPAIR_INPUT", "deploy/distill/phase2/outputs/pilot.verified.jsonl"))
    output_path = Path(env_value(args, "output", "REPAIR_OUTPUT", "deploy/distill/phase2/outputs/pilot.repaired.jsonl"))
    host = env_value(args, "host", "HOST", "127.0.0.1")
    port = env_value(args, "port", "PORT", "8080")
    model = env_value(args, "model", "REPAIR_MODEL", "phase2-repair-teacher")
    timeout = env_float(args, "timeout", "TIMEOUT", 300.0)
    max_tokens = env_int(args, "max_tokens", "REPAIR_MAX_TOKENS", 2048)
    temperature = env_float(args, "temperature", "REPAIR_TEMPERATURE", 0.2)
    top_p = env_float(args, "top_p", "REPAIR_TOP_P", 0.95)
    api_key = os.environ.get(args.api_key_env)
    url = f"http://{host}:{port}/v1/chat/completions"
    repair_offset = args.offset if args.offset is not None else int(os.environ.get("REPAIR_OFFSET", "0"))
    max_repairs = args.max_repairs
    if max_repairs is None and os.environ.get("REPAIR_MAX_REPAIRS"):
        max_repairs = int(os.environ["REPAIR_MAX_REPAIRS"])
    if repair_offset < 0:
        raise SystemExit("--offset must be >= 0")
    if max_repairs is not None and max_repairs < 1:
        raise SystemExit("--max-repairs must be >= 1")
    ids_filter = load_ids(Path(args.ids_file)) if args.ids_file else None

    samples = load_jsonl(input_path)
    repairable = [sample for sample in samples if should_repair(sample, args.include_unverified)]
    if ids_filter is not None:
        repairable = [sample for sample in repairable if sample.get("id") in ids_filter]
    selected_repairable = repairable[repair_offset:]
    if max_repairs is not None:
        selected_repairable = selected_repairable[:max_repairs]
    selected_ids = {sample["id"] for sample in selected_repairable}
    if args.dry_run:
        print(json.dumps({
            "input": str(input_path),
            "output": str(output_path),
            "url": url,
            "repairable": [sample["id"] for sample in repairable],
            "selected_repairable": [sample["id"] for sample in selected_repairable],
            "offset": repair_offset,
            "max_repairs": max_repairs,
            "api_key_configured": bool(api_key),
        }, indent=2))
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as out:
        for sample in samples:
            if sample.get("id") in selected_ids:
                repaired = repair_sample(sample, url, model, api_key, timeout, max_tokens, temperature, top_p)
                repair_meta = repaired.get("verification", {}).get("repair", {})
                print(f"{sample['id']}: cause={repair_meta.get('failure_cause')} target={repair_meta.get('repair_target')} applied={repair_meta.get('applied')}")
                out.write(json.dumps(repaired, ensure_ascii=False) + "\n")
            else:
                out.write(json.dumps(sample, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
