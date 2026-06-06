"""Map KodCode/KodCode-V1-SFT-4o rows to the local distill JSONL schema."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from common import detect_language, fingerprint, kodcode_task_type, normalize_text


FENCE_RE = re.compile(r"```(?P<label>[A-Za-z0-9_+.-]*)\n(?P<body>.*?)```", re.DOTALL)


def _assistant_text(row: dict[str, Any]) -> str:
    conversations = row.get("conversations") or []
    for turn in conversations:
        if isinstance(turn, dict) and turn.get("from") in {"gpt", "assistant"}:
            value = turn.get("value")
            if isinstance(value, str) and value.strip():
                return value.strip()
    solution = row.get("solution")
    if isinstance(solution, str) and solution.strip():
        return solution.strip()
    alt = row.get("4o_solution")
    if isinstance(alt, str) and alt.strip():
        return alt.strip()
    return ""


def _user_text(row: dict[str, Any]) -> str:
    question = row.get("question")
    if isinstance(question, str) and question.strip():
        return question.strip()
    conversations = row.get("conversations") or []
    for turn in conversations:
        if isinstance(turn, dict) and turn.get("from") in {"human", "user"}:
            value = turn.get("value")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _code(row: dict[str, Any]) -> str:
    solution = row.get("solution")
    if isinstance(solution, str) and solution.strip():
        return solution.strip()
    alt = row.get("4o_solution")
    if isinstance(alt, str) and alt.strip():
        return alt.strip()
    assistant = _assistant_text(row)
    fences = [match.group("body").strip() for match in FENCE_RE.finditer(assistant)]
    if fences:
        return fences[0]
    return assistant


def _tests(row: dict[str, Any]) -> str:
    test_code = row.get("test_code")
    if isinstance(test_code, str):
        return test_code.strip()
    return ""


def _row_id(row: dict[str, Any], row_index: int) -> str:
    for key in ("question_id", "conversation_id"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
            return f"kodcode_{safe}"
    return f"kodcode_row_{row_index:08d}"


def normalize_row(
    row: dict[str, Any],
    *,
    dataset_id: str,
    revision: str,
    license_name: str,
    uri: str,
    row_index: int,
) -> dict[str, Any] | None:
    prompt = _user_text(row)
    code = _code(row)
    tests = _tests(row)
    if not prompt or not code:
        return None

    language = detect_language(code, prompt)
    subset = str(row.get("subset") or "unknown")
    style = str(row.get("style") or "instruct")
    now = datetime.now(timezone.utc).isoformat()
    sample_id = _row_id(row, row_index)

    return {
        "id": sample_id,
        "task_type": kodcode_task_type(subset, style),
        "language": language,
        "source": {
            "kind": "huggingface",
            "license": license_name,
            "uri": f"{uri}@revision={revision}",
            "tier": None,
        },
        "prompt": prompt,
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": _assistant_text(row) or code},
        ],
        "reasoning": "",
        "code": code,
        "tests": tests,
        "verification": {
            "compile": None,
            "lint": None,
            "tests": None,
            "score": None,
        },
        "meta": {
            "teacher": None,
            "generated_at": now,
            "upstream": {
                "dataset_id": dataset_id,
                "revision": revision,
                "row_index": row_index,
                "original_id": row.get("question_id") or row.get("conversation_id"),
                "subset": subset,
                "style": style,
                "4o_correctness": row.get("4o_correctness"),
                "gpt_difficulty": row.get("gpt_difficulty"),
            },
            "prompt_fingerprint": fingerprint(prompt),
            "prompt_normalized": normalize_text(prompt),
        },
    }
