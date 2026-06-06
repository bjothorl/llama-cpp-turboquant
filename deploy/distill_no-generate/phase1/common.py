"""Shared helpers for distill_no-generate phase 1."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterator


REPO = Path(__file__).resolve().parents[3]
TRACK = Path(__file__).resolve().parents[1]
DATASETS_CONFIG = Path(__file__).resolve().parent / "datasets.json"


def load_datasets_config() -> dict[str, Any]:
    return json.loads(DATASETS_CONFIG.read_text())


def dataset_config(dataset_id: str) -> dict[str, Any]:
    config = load_datasets_config()
    if dataset_id not in config:
        raise SystemExit(f"unknown dataset {dataset_id!r}; add it to {DATASETS_CONFIG}")
    return config[dataset_id]


def slugify_dataset_id(dataset_id: str) -> str:
    return dataset_id.replace("/", "__")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows: Iterator[dict[str, Any]] | list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(row, ensure_ascii=False) + "\n")


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


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def detect_language(code: str, question: str = "") -> str:
    code_lower = code.lower()
    if re.search(r"\bdef \w+\(", code) or "import pytest" in code_lower or "from solution import" in code_lower:
        return "python"
    if re.search(r"\b(export )?(function|const|class) \w+", code) or re.search(r":\s*(string|number|boolean)\b", code):
        return "typescript"
    if re.search(r"\bfunction \w+\(", code) and "def " not in code:
        return "javascript"
    if "def " in code:
        return "python"
    return "python"


def kodcode_task_type(subset: str, style: str) -> str:
    subset_key = (subset or "unknown").strip().lower().replace(" ", "_")
    style_key = (style or "instruct").strip().lower()
    if style_key == "complete":
        return f"kodcode_{subset_key}_complete"
    return f"kodcode_{subset_key}"
