#!/usr/bin/env python3
"""One-off helper to build no-repair prompt JSONL files. Safe to re-run."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EXPANDED = REPO / "deploy/distill/phase1/prompts/expanded_pilot_tasks.jsonl"
PILOT = REPO / "deploy/distill/phase1/prompts/pilot_tasks.jsonl"
PROMPTS = Path(__file__).resolve().parent / "prompts"

HARD_IDS = {
    "expanded_react_component_002",
    "expanded_react_component_003",
    "expanded_zod_schema_003",
}

NEW_TASKS = [
    {
        "id": "nr_ts_bugfix_001",
        "task_type": "typescript_bugfix",
        "language": "typescript",
        "tier": "revised",
        "prompt": (
            "Fix the bug in this TypeScript function. Preserve the public API and return only production code.\n\n"
            "```ts\n"
            "export function clamp(value: number, min: number, max: number): number {\n"
            "  if (value < min) return min;\n"
            "  if (value > max) return max;\n"
            "  return min;\n"
            "}\n"
            "```"
        ),
    },
    {
        "id": "nr_ts_bugfix_002",
        "task_type": "typescript_bugfix",
        "language": "typescript",
        "tier": "revised",
        "prompt": (
            "Fix the bug in this TypeScript function. It should return the last `n` items without mutating the input. "
            "Return only production code.\n\n"
            "```ts\n"
            "export function takeLast<T>(items: T[], n: number): T[] {\n"
            "  return items.slice(0, n);\n"
            "}\n"
            "```"
        ),
    },
    {
        "id": "nr_ts_bugfix_003",
        "task_type": "typescript_bugfix",
        "language": "typescript",
        "tier": "revised",
        "prompt": (
            "Fix the bug in this TypeScript function. It should compute a percentage rounded to two decimal places. "
            "Return only production code.\n\n"
            "```ts\n"
            "export function percent(part: number, whole: number): number {\n"
            "  return Math.round((part / whole) * 100) / 100;\n"
            "}\n"
            "```"
        ),
    },
    {
        "id": "nr_ts_refactor_001",
        "task_type": "typescript_refactor",
        "language": "typescript",
        "tier": "revised",
        "prompt": (
            "Refactor this TypeScript function for clarity without changing behavior. Preserve the public API "
            "and return only production code.\n\n"
            "```ts\n"
            "export function isValidEmail(value: string): boolean {\n"
            "  if (value.indexOf('@') > 0) {\n"
            "    if (value.indexOf('.') > value.indexOf('@') + 1) {\n"
            "      return true;\n"
            "    }\n"
            "  }\n"
            "  return false;\n"
            "}\n"
            "```"
        ),
    },
    {
        "id": "nr_ts_refactor_002",
        "task_type": "typescript_refactor",
        "language": "typescript",
        "tier": "revised",
        "prompt": (
            "Refactor this TypeScript function to remove duplication without changing behavior. "
            "Return only production code.\n\n"
            "```ts\n"
            "export function badgeClass(kind: 'info' | 'warn' | 'error'): string {\n"
            "  if (kind === 'info') return 'badge badge-info';\n"
            "  if (kind === 'warn') return 'badge badge-warn';\n"
            "  if (kind === 'error') return 'badge badge-error';\n"
            "  return 'badge';\n"
            "}\n"
            "```"
        ),
    },
    {
        "id": "nr_ts_refactor_003",
        "task_type": "typescript_refactor",
        "language": "typescript",
        "tier": "revised",
        "prompt": (
            "Refactor this TypeScript helper into smaller functions without changing behavior. "
            "Return only production code.\n\n"
            "```ts\n"
            "export function parseCsvLine(line: string): string[] {\n"
            "  const out: string[] = [];\n"
            "  let current = '';\n"
            "  let inQuotes = false;\n"
            "  for (let i = 0; i < line.length; i++) {\n"
            "    const ch = line[i];\n"
            "    if (ch === '\"') inQuotes = !inQuotes;\n"
            "    else if (ch === ',' && !inQuotes) { out.push(current); current = ''; }\n"
            "    else current += ch;\n"
            "  }\n"
            "  out.push(current);\n"
            "  return out;\n"
            "}\n"
            "```"
        ),
    },
    {
        "id": "nr_zod_schema_001",
        "task_type": "zod_schema",
        "language": "typescript",
        "tier": "revised",
        "prompt": (
            "Create only the TypeScript implementation for a Zod schema `InviteUserSchema` with `email` and `role` "
            "where role is `admin` or `member`. Validate email format, trim strings, and export the inferred type."
        ),
    },
    {
        "id": "nr_zod_schema_002",
        "task_type": "zod_schema",
        "language": "typescript",
        "tier": "revised",
        "prompt": (
            "Create only the TypeScript implementation for a Zod schema `TagListSchema` as an array of non-empty "
            "trimmed strings with at most 10 items. Export the inferred type."
        ),
    },
    {
        "id": "nr_zod_schema_003",
        "task_type": "zod_schema",
        "language": "typescript",
        "tier": "revised",
        "prompt": (
            "Create only the TypeScript implementation for a Zod schema `UpdateProfileSchema` with optional "
            "`displayName` and `bio`. Trim strings, limit bio to 280 characters when provided, and export the inferred type."
        ),
    },
    {
        "id": "nr_react_component_001",
        "task_type": "react_component",
        "language": "typescript",
        "tier": "revised",
        "prompt": (
            "Write only the React TypeScript implementation for a presentational component `StatusBadge` with props "
            "`{ label: string; tone: 'neutral' | 'success' | 'danger' }`. Render accessible text; no internal state."
        ),
    },
    {
        "id": "nr_react_component_002",
        "task_type": "react_component",
        "language": "typescript",
        "tier": "revised",
        "prompt": (
            "Write only the React TypeScript implementation for a controlled component `TextField` with props "
            "`{ value: string; onChange: (value: string) => void; label: string; error?: string }`. "
            "Associate the label with the input; no timers or network calls."
        ),
    },
    {
        "id": "nr_react_component_003",
        "task_type": "react_component",
        "language": "typescript",
        "tier": "revised",
        "prompt": (
            "Write only the React TypeScript implementation for a component `ConfirmDialog` with props "
            "`{ open: boolean; title: string; message: string; onConfirm: () => void; onCancel: () => void }`. "
            "Render nothing when closed; no portals required."
        ),
    },
]

CALIBRATE_IDS = [
    "expanded_ts_bugfix_001",
    "expanded_refactor_002",
    "expanded_react_component_004",
    "expanded_zod_schema_002",
    "nr_ts_bugfix_001",
    "nr_zod_schema_001",
    "nr_react_component_001",
    "expanded_react_component_002",
    "expanded_zod_schema_003",
    "nr_ts_refactor_001",
]


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def with_tier(row: dict, tier: str) -> dict:
    out = dict(row)
    source = dict(out.get("source") or {})
    source["tier"] = tier
    out["source"] = source
    return out


def to_task_row(spec: dict) -> dict:
    return {
        "id": spec["id"],
        "task_type": spec["task_type"],
        "language": spec["language"],
        "source": {
            "kind": "synthetic_template",
            "license": "local",
            "uri": None,
            "tier": spec["tier"],
        },
        "prompt": spec["prompt"],
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def main() -> None:
    expanded_ts = [r for r in load_jsonl(EXPANDED) if r.get("language") == "typescript"]
    pilot_ts = [r for r in load_jsonl(PILOT) if r.get("language") == "typescript"]

    write_jsonl(PROMPTS / "pilot_tasks.jsonl", [with_tier(r, "proven") for r in pilot_ts])
    write_jsonl(PROMPTS / "typescript_tasks.jsonl", [with_tier(r, "proven") for r in expanded_ts])

    hard = [with_tier(r, "baseline") for r in expanded_ts if r["id"] in HARD_IDS]
    write_jsonl(PROMPTS / "typescript_tasks_hard.jsonl", hard)

    core = [with_tier(r, "proven") for r in expanded_ts if r["id"] not in HARD_IDS]
    core.extend(to_task_row(spec) for spec in NEW_TASKS)
    core.extend(with_tier(r, "baseline") for r in expanded_ts if r["id"] in HARD_IDS)
    write_jsonl(PROMPTS / "typescript_tasks_30.jsonl", core)

    by_id = {r["id"]: r for r in core}
    by_id.update({r["id"]: with_tier(r, "proven") for r in expanded_ts})
    calibrate = [by_id[i] for i in CALIBRATE_IDS if i in by_id]
    write_jsonl(PROMPTS / "typescript_tasks_calibrate.jsonl", calibrate)

    print(f"pilot_tasks.jsonl: {len(pilot_ts)}")
    print(f"typescript_tasks.jsonl: {len(expanded_ts)}")
    print(f"typescript_tasks_30.jsonl: {len(core)}")
    print(f"typescript_tasks_calibrate.jsonl: {len(calibrate)}")
    print(f"typescript_tasks_hard.jsonl: {len(hard)}")


if __name__ == "__main__":
    main()
