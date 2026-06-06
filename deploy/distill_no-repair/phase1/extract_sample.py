#!/usr/bin/env python3
"""Helpers for extracting structured fields from teacher responses."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


FENCE_RE = re.compile(r"```(?P<label>[A-Za-z0-9_+.-]*)\n(?P<body>.*?)```", re.DOTALL)
THINK_RE = re.compile(r"<think>(?P<body>.*?)</think>", re.DOTALL | re.IGNORECASE)
TEST_HINT_RE = re.compile(r"\b(pytest|unittest|vitest|jest|describe\(|it\(|test\(|expect\()", re.IGNORECASE)


def assistant_message(response: dict[str, Any] | None) -> dict[str, Any]:
    if not response:
        return {}
    choices = response.get("choices") or []
    if not choices:
        return {}
    message = choices[0].get("message") or {}
    return message if isinstance(message, dict) else {}


def extract_reasoning(message: dict[str, Any]) -> str:
    reasoning = message.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning.strip()
    content = message.get("content") or ""
    match = THINK_RE.search(content)
    return match.group("body").strip() if match else ""


def strip_think(content: str) -> str:
    return THINK_RE.sub("", content).strip()


def extract_fences(content: str) -> list[dict[str, str]]:
    fences: list[dict[str, str]] = []
    for match in FENCE_RE.finditer(content):
        fences.append({
            "label": match.group("label").strip().lower(),
            "body": match.group("body").strip(),
        })
    return fences


def preferred_code(fences: list[dict[str, str]], language: str | None = None) -> str:
    if not fences:
        return ""
    language = (language or "").lower()
    aliases = {
        "typescript": {"ts", "tsx", "typescript"},
        "javascript": {"js", "jsx", "javascript"},
        "python": {"py", "python"},
    }.get(language, {language} if language else set())
    for fence in fences:
        if fence["label"] in aliases:
            return fence["body"]
    return fences[0]["body"]


def preferred_tests(fences: list[dict[str, str]], content: str) -> str:
    for fence in fences:
        label = fence["label"]
        body = fence["body"]
        if label in {"test", "tests", "spec", "py", "python", "ts", "tsx", "typescript", "js", "javascript"} and TEST_HINT_RE.search(body):
            return body
    for fence in fences:
        if TEST_HINT_RE.search(fence["body"]):
            return fence["body"]
    if TEST_HINT_RE.search(content):
        return content.strip()
    return ""


def parse_response(response: dict[str, Any] | None, language: str | None = None) -> dict[str, Any]:
    message = assistant_message(response)
    content = message.get("content") or ""
    clean_content = strip_think(content)
    fences = extract_fences(clean_content)
    return {
        "content": clean_content,
        "reasoning": extract_reasoning(message),
        "fences": fences,
        "code": preferred_code(fences, language),
        "tests": preferred_tests(fences, clean_content),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response", help="Path to a JSON response file")
    parser.add_argument("--language", default=None)
    args = parser.parse_args()

    response = json.loads(Path(args.response).read_text())
    print(json.dumps(parse_response(response, args.language), indent=2))


if __name__ == "__main__":
    main()
