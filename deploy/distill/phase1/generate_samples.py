#!/usr/bin/env python3
"""Generate a small Phase 1 raw JSONL corpus from a local teacher server."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from extract_sample import parse_response


DEFAULT_ENV_FILE = Path(__file__).resolve().parent / "generator.env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="Optional KEY=VALUE env file")
    parser.add_argument("--prompts", default=None, help="JSONL task file")
    parser.add_argument("--output", default=None, help="Append-only output JSONL")
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--teacher-id", default=None)
    parser.add_argument("--candidates", type=int, default=None, help="Generate this many candidates per prompt")
    parser.add_argument("--api-key-env", default="LLAMA_API_KEY")
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Validate prompts and print planned requests without calling the server")
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


def env_value(args: argparse.Namespace, attr: str, env_name: str, default: str | None = None) -> str:
    value = getattr(args, attr)
    if value is not None:
        return str(value)
    value = os.environ.get(env_name)
    if value is not None:
        return value
    if default is not None:
        return default
    raise SystemExit(f"missing required value: --{attr.replace('_', '-')} or {env_name}")


def env_int(args: argparse.Namespace, attr: str, env_name: str, default: int) -> int:
    value = getattr(args, attr)
    if value is not None:
        return int(value)
    return int(os.environ.get(env_name, default))


def env_float(args: argparse.Namespace, attr: str, env_name: str, default: float) -> float:
    value = getattr(args, attr)
    if value is not None:
        return float(value)
    return float(os.environ.get(env_name, default))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        for key in ("id", "task_type", "language", "source", "prompt"):
            if key not in row:
                raise SystemExit(f"{path}:{line_no}: missing required key {key!r}")
        rows.append(row)
    return rows


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
    except Exception as exc:  # noqa: BLE001 - diagnostic generator
        return 0, None, str(exc)


def completion_payload(
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
    top_p: float,
    enable_thinking: bool,
    reasoning_format: str,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "chat_template_kwargs": {
            "enable_thinking": enable_thinking,
        },
        "reasoning_format": reasoning_format,
    }


def generate_one(
    task: dict[str, Any],
    url: str,
    model: str,
    teacher_id: str,
    api_key: str | None,
    timeout: float,
    max_tokens_solve: int,
    max_tokens_tests: int,
    temperature: float,
    top_p: float,
    enable_thinking: bool,
    reasoning_format: str,
) -> dict[str, Any]:
    solve_messages = [
        {
            "role": "system",
            "content": (
                "You generate high-quality coding training data. "
                "Answer directly. Do not include hidden reasoning or chain-of-thought. "
                "Return exactly one production-ready code block. "
                "Do not include tests, example usage, console logging, markdown sections, or extra prose unless the user explicitly asks for explanation."
            ),
        },
        {
            "role": "user",
            "content": (
                f"{task['prompt']}\n\n"
                "Important: this is the solution turn only. Do not include tests; tests will be requested separately."
            ),
        },
    ]
    solve_payload = completion_payload(
        model,
        solve_messages,
        max_tokens_solve,
        temperature,
        top_p,
        enable_thinking,
        reasoning_format,
    )
    solve_started = time.monotonic()
    solve_status, solve_response, solve_error = post_json(url, solve_payload, api_key, timeout)
    solve_latency = time.monotonic() - solve_started
    solve_parsed = parse_response(solve_response, task.get("language"))

    test_prompt = (
        "Write focused tests for the solution below. "
        "Prefer the dominant test framework for the language. "
        "Return exactly one fenced code block containing only test code. "
        "Do not restate the solution. Do not redefine the implementation under test unless unavoidable. "
        "Do not include markdown sections or explanatory prose.\n\n"
        f"Original task:\n{task['prompt']}\n\n"
        f"Solution:\n{solve_parsed['content']}"
    )
    test_messages = [
        {
            "role": "system",
            "content": (
                "You write concise, executable tests for coding tasks. "
                "Answer directly with exactly one fenced code block and no hidden reasoning."
            ),
        },
        {"role": "user", "content": test_prompt},
    ]
    test_payload = completion_payload(
        model,
        test_messages,
        max_tokens_tests,
        temperature,
        top_p,
        enable_thinking,
        reasoning_format,
    )
    test_started = time.monotonic()
    test_status, test_response, test_error = post_json(url, test_payload, api_key, timeout)
    test_latency = time.monotonic() - test_started
    test_parsed = parse_response(test_response, task.get("language"))

    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": task["id"],
        "task_type": task["task_type"],
        "language": task["language"],
        "source": task["source"],
        "prompt": task["prompt"],
        "messages": solve_messages + [
            {
                "role": "assistant",
                "content": solve_parsed["content"],
            }
        ],
        "reasoning": solve_parsed["reasoning"],
        "code": solve_parsed["code"],
        "tests": test_parsed["tests"] or test_parsed["code"],
        "verification": {
            "compile": None,
            "lint": None,
            "tests": None,
            "score": None,
        },
        "meta": {
            "teacher": teacher_id,
            "generated_at": now,
            "sampling": {
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens_solve": max_tokens_solve,
                "max_tokens_tests": max_tokens_tests,
                "enable_thinking": enable_thinking,
                "reasoning_format": reasoning_format,
            },
            "turns": {
                "solve": {
                    "http_status": solve_status,
                    "latency_s": solve_latency,
                    "error": solve_error,
                    "raw": solve_response,
                },
                "tests": {
                    "http_status": test_status,
                    "latency_s": test_latency,
                    "error": test_error,
                    "raw": test_response,
                },
            },
        },
    }


def main() -> None:
    args = parse_args()
    load_env_file(Path(args.env_file))

    prompts_path = Path(env_value(args, "prompts", "PROMPTS", "deploy/distill/phase1/prompts/pilot_tasks.jsonl"))
    output_path = Path(env_value(args, "output", "OUTPUT", "deploy/distill/phase1/outputs/pilot.jsonl"))
    host = env_value(args, "host", "HOST", "127.0.0.1")
    port = env_value(args, "port", "PORT", "8080")
    model = env_value(args, "model", "MODEL", "phase1-teacher")
    teacher_id = env_value(args, "teacher_id", "TEACHER_ID", model)
    max_samples = env_int(args, "max_samples", "MAX_SAMPLES", 5)
    candidates = env_int(args, "candidates", "CANDIDATES", 1)
    if candidates < 1:
        raise SystemExit("--candidates must be >= 1")
    timeout = env_float(args, "timeout", "TIMEOUT", 300.0)
    max_tokens_solve = int(os.environ.get("MAX_TOKENS_SOLVE", "1536"))
    max_tokens_tests = int(os.environ.get("MAX_TOKENS_TESTS", "1024"))
    temperature = float(os.environ.get("TEMPERATURE", "0.6"))
    top_p = float(os.environ.get("TOP_P", "0.95"))
    enable_thinking = os.environ.get("ENABLE_THINKING", "false").strip().lower() in {"1", "true", "yes", "on"}
    reasoning_format = os.environ.get("REASONING_FORMAT", "deepseek")
    api_key = os.environ.get(args.api_key_env)
    url = f"http://{host}:{port}/v1/chat/completions"

    tasks = load_jsonl(prompts_path)[:max_samples]
    total = len(tasks) * candidates
    if args.dry_run:
        print(json.dumps({
            "url": url,
            "output": str(output_path),
            "tasks": [task["id"] for task in tasks],
            "candidates_per_task": candidates,
            "total_samples": total,
            "api_key_configured": bool(api_key),
        }, indent=2))
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as out:
        idx = 0
        for task in tasks:
            for candidate in range(1, candidates + 1):
                idx += 1
                candidate_task = dict(task)
                if candidates > 1:
                    candidate_task["id"] = f"{task['id']}_c{candidate:02d}"
                sample = generate_one(
                    task=candidate_task,
                    url=url,
                    model=model,
                    teacher_id=teacher_id,
                    api_key=api_key,
                    timeout=timeout,
                    max_tokens_solve=max_tokens_solve,
                    max_tokens_tests=max_tokens_tests,
                    temperature=temperature,
                    top_p=top_p,
                    enable_thinking=enable_thinking,
                    reasoning_format=reasoning_format,
                )
                if candidates > 1:
                    sample["meta"]["source_task_id"] = task["id"]
                    sample["meta"]["candidate"] = candidate
                    sample["meta"]["candidates_per_task"] = candidates
                out.write(json.dumps(sample, ensure_ascii=False) + "\n")
                solve_status = sample["meta"]["turns"]["solve"]["http_status"]
                test_status = sample["meta"]["turns"]["tests"]["http_status"]
                print(
                    f"{idx}/{total} {sample['id']}: "
                    f"solve={solve_status} tests={test_status} "
                    f"code_chars={len(sample['code'])} tests_chars={len(sample['tests'])}"
                )


if __name__ == "__main__":
    main()
