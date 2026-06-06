# TypeScript prompt design (no-repair track)

Guidance for [`typescript_tasks_30.jsonl`](typescript_tasks_30.jsonl) and calibration. Based on the mixed-language 50× run in [`deploy/distill/`](../../distill/) (614/1500 passed, 40.9%).

## What worked well

- **Bugfix** with embedded broken snippet and stable API (~75–92% per task).
- **Refactor** with full code provided (~90%+ on several tasks).
- **Presentational React** without async or timers (`DismissibleAlert` ~64%).
- **Straightforward Zod** field validation (trim, email, enums).

## What struggled

- **Async React** (`AsyncSaveButton` 0/50).
- **Debounce / timers** (`DebouncedSearchInput` ~14%).
- **Zod query coercion** (`PaginationQuerySchema` ~4%).
- **Heavy a11y test expectations** on simple components.

Failures skew toward `node:vitest` over `typescript:tsc` — improve **test-generation** instructions globally, not per failing task ID.

## Anti-overfitting rules

**Do**

- Adjust **category templates** for all bugfix / zod / react prompts.
- Rebalance task mix (~40% bugfix+refactor, ~30% zod, ~30% react).
- Use `source.tier`: `proven`, `revised`, `baseline`, `experimental`.
- Keep [`typescript_tasks_hard.jsonl`](typescript_tasks_hard.jsonl) for regression benchmarks.

**Don't**

- Paste verifier stderr or repair notes into prompts.
- Add task-specific cheats tied to one ID.
- Drop hard tasks entirely (inflates pass rate, hurts generalization).

## Task ID prefixes

| Prefix | Meaning |
|--------|---------|
| `expanded_*` | From [`deploy/distill/phase1/prompts/expanded_pilot_tasks.jsonl`](../../../distill/phase1/prompts/expanded_pilot_tasks.jsonl) |
| `nr_*` | **No-repair track** tasks authored in [`build_prompts.py`](../build_prompts.py) (`NEW_TASKS`) |

## Tier tags

| Tier | Meaning |
|------|---------|
| `proven` | Carried from expanded pilot with decent pass rate |
| `revised` | New or rewritten category template in this track (`nr_*` tasks) |
| `baseline` | Hard anchor tasks kept for regression (e.g. async React); **6.7%** on full 30×50 — exclude from SFT mix |

## Calibration gate

After ~50 samples (10 tasks × 5 candidates):

- Below ~35% overall → revise category templates or `TEST_SYSTEM_PROMPT` in `generate_samples.py`, not individual IDs.
- ~40–50%+ → proceed to full 18×50 or 30×50 run.

**Full 30×50 (2026-05-25):** 784/1500 (**52.3%**). Weakest: `expanded_zod_schema_003`, `nr_zod_schema_001` (0/50 each). See [`../../PLAN.md`](../../PLAN.md).
