#!/usr/bin/env python3
"""Run Phase 0 coding smoke prompts against llama-server."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_ENV_FILE = Path(__file__).resolve().parent / "models.env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="Run artifact directory")
    parser.add_argument("--prompts", required=True, help="JSONL prompt file")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="8080")
    parser.add_argument("--model", default="phase0")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="Optional KEY=VALUE env file to read")
    parser.add_argument("--api-key-env", default="LLAMA_API_KEY", help="Environment variable containing the bearer token")
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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return rows


def post_json(
    url: str,
    payload: dict[str, Any],
    timeout: float,
    api_key: str | None,
) -> tuple[int, dict[str, Any] | None, str | None]:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url,
        data=data,
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
    except Exception as exc:  # noqa: BLE001 - this is a diagnostic script
        return 0, None, str(exc)


def message_content(response: dict[str, Any] | None) -> tuple[str, str | None]:
    if not response:
        return "", None
    choices = response.get("choices") or []
    if not choices:
        return "", None
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    reasoning = message.get("reasoning_content")
    return content, reasoning


def timing_metrics(response: dict[str, Any] | None, latency_s: float) -> dict[str, Any]:
    if not response:
        return {"completion_tokens": None, "tokens_per_second": None}
    usage = response.get("usage") or {}
    completion_tokens = usage.get("completion_tokens")
    timings = response.get("timings") or {}
    predicted_n = timings.get("predicted_n")
    predicted_ms = timings.get("predicted_ms")
    tokens_per_second = None
    if predicted_n is not None and predicted_ms:
        tokens_per_second = float(predicted_n) / (float(predicted_ms) / 1000.0)
    elif completion_tokens and latency_s > 0:
        tokens_per_second = float(completion_tokens) / latency_s
    return {
        "completion_tokens": completion_tokens,
        "tokens_per_second": tokens_per_second,
        "timings": timings or None,
    }


def repeated_warning(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) >= 6:
        counts: dict[str, int] = {}
        for line in lines:
            counts[line] = counts.get(line, 0) + 1
            if counts[line] >= 4:
                return True
    words = text.split()
    if len(words) >= 20:
        run = 1
        last = words[0]
        for word in words[1:]:
            if word == last:
                run += 1
                if run >= 12:
                    return True
            else:
                run = 1
                last = word
    return False


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [row for row in records if row["http_status"] == 200]
    tps_values = [
        row["metrics"]["tokens_per_second"]
        for row in successful
        if row["metrics"].get("tokens_per_second") is not None
    ]
    return {
        "total": len(records),
        "ok": len(successful),
        "failed": len(records) - len(successful),
        "code_fence_count": sum(1 for row in successful if row["checks"]["has_code_fence"]),
        "reasoning_count": sum(1 for row in successful if row["checks"]["has_reasoning"]),
        "repetition_warnings": sum(1 for row in successful if row["checks"]["repetition_warning"]),
        "avg_latency_s": sum(row["latency_s"] for row in records) / len(records) if records else None,
        "avg_tokens_per_second": sum(tps_values) / len(tps_values) if tps_values else None,
    }


def write_markdown(run_dir: Path, summary: dict[str, Any], records: list[dict[str, Any]]) -> None:
    lines = [
        "# Smoke Summary",
        "",
        f"- Total prompts: {summary['total']}",
        f"- HTTP 200: {summary['ok']}",
        f"- Failed: {summary['failed']}",
        f"- Code fences: {summary['code_fence_count']}",
        f"- Reasoning fields: {summary['reasoning_count']}",
        f"- Repetition warnings: {summary['repetition_warnings']}",
        f"- Average latency seconds: {summary['avg_latency_s']}",
        f"- Average tokens/sec: {summary['avg_tokens_per_second']}",
        "",
        "| ID | Category | Status | Latency s | Tok/s | Checks |",
        "|----|----------|--------|-----------|-------|--------|",
    ]
    for row in records:
        checks = []
        if row["checks"]["has_code_fence"]:
            checks.append("code_fence")
        if row["checks"]["has_reasoning"]:
            checks.append("reasoning")
        if row["checks"]["repetition_warning"]:
            checks.append("repetition_warning")
        lines.append(
            "| {id} | {category} | {status} | {latency:.3f} | {tps} | {checks} |".format(
                id=row["id"],
                category=row["category"],
                status=row["http_status"],
                latency=row["latency_s"],
                tps=row["metrics"].get("tokens_per_second"),
                checks=", ".join(checks) if checks else "-",
            )
        )
    (run_dir / "smoke_summary.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    args = parse_args()
    load_env_file(Path(args.env_file))
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    prompts = load_jsonl(Path(args.prompts))
    url = f"http://{args.host}:{args.port}/v1/chat/completions"
    api_key = os.environ.get(args.api_key_env)

    records: list[dict[str, Any]] = []
    responses_path = run_dir / "responses.jsonl"
    with responses_path.open("w", encoding="utf-8") as out:
        for prompt in prompts:
            payload = {
                "model": args.model,
                "messages": prompt["messages"],
                "temperature": args.temperature,
                "max_tokens": args.max_tokens,
            }
            started = time.monotonic()
            status, response, error = post_json(url, payload, args.timeout, api_key)
            latency = time.monotonic() - started
            content, reasoning = message_content(response)
            record = {
                "id": prompt.get("id"),
                "category": prompt.get("category"),
                "http_status": status,
                "latency_s": latency,
                "error": error,
                "checks": {
                    "has_code_fence": "```" in content,
                    "has_reasoning": bool(reasoning),
                    "repetition_warning": repeated_warning(content),
                    "content_chars": len(content),
                },
                "metrics": timing_metrics(response, latency),
                "response": response,
            }
            records.append(record)
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"{record['id']}: status={status} latency={latency:.2f}s")

    summary = summarize(records)
    (run_dir / "smoke_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    write_markdown(run_dir, summary, records)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
