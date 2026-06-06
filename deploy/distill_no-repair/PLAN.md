# TypeScript verify-only distillation (prototype)

Fast path for local coding SFT data without the repair loop in [`deploy/distill/`](../distill/). Full MTP roadmap and mixed-language 50× results: [`deploy/distill/PLAN.md`](../distill/PLAN.md).

## Scope

- **TypeScript only** (bugfix, refactor, React, Zod).
- **Two-turn generation**: solution, then tests.
- **Full verification**: `tsc --noEmit`, Vitest (`INSTALL_NODE_DEPS=true`).
- **Select passed** samples into `solution_sft.jsonl`.
- **No repair** — first-pass verify yield ~52% on full 30×50 run; improve prompts and harness on weak tasks.

## Workflow

1. **Smoke** — 3 tasks × 1 candidate: [`phase1/prompts/pilot_tasks.jsonl`](phase1/prompts/pilot_tasks.jsonl)
2. **Calibrate** — 10 tasks × 5 candidates = 50: [`run_calibrate.sh`](run_calibrate.sh)
3. **Scale** — 30 tasks × 50 = 1500 (or 18×50 = 900): [`run_pipeline.sh`](run_pipeline.sh)

## Prompt files

| File | Tasks | Use |
|------|------:|-----|
| `pilot_tasks.jsonl` | 3 | Smoke |
| `typescript_tasks.jsonl` | 18 | Baseline (900 @ 50×) |
| `typescript_tasks_30.jsonl` | 30 | Curated mix (1500 @ 50×) |
| `typescript_tasks_calibrate.jsonl` | 10 | Calibration |
| `typescript_tasks_hard.jsonl` | 3 | Benchmark only (not in default training mix) |

See [`phase1/prompts/PROMPT_DESIGN.md`](phase1/prompts/PROMPT_DESIGN.md).

**Task ID prefixes:** `expanded_*` = tasks from [`deploy/distill/phase1/prompts/expanded_pilot_tasks.jsonl`](../distill/phase1/prompts/expanded_pilot_tasks.jsonl). `nr_*` = **no-repair track** tasks added in [`phase1/build_prompts.py`](phase1/build_prompts.py) (`NEW_TASKS`, tier `revised`).

## Execution status (2026-05-25)

### Done

- Pipeline scaffold, harness fixes, calibration (50 samples).
- **Full 30×50 run** via [`run_pipeline.sh`](run_pipeline.sh): generate → verify → select.
- **`TEST_SYSTEM_PROMPT`** inlined in [`phase1/generate_samples.py`](phase1/generate_samples.py) (no `TESTS_TURN_HINT` env).

### Full run — 30 tasks × 50 candidates (1500)

| Artifact | Path |
|----------|------|
| Raw | [`phase1/outputs/typescript_candidates_50x.jsonl`](phase1/outputs/typescript_candidates_50x.jsonl) |
| Verified | [`phase2/outputs/typescript_candidates_50x.verified.jsonl`](phase2/outputs/typescript_candidates_50x.verified.jsonl) |
| SFT export | [`phase2/outputs/solution_sft.jsonl`](phase2/outputs/solution_sft.jsonl) (**256** rows, cap 10/task) |

| Metric | Value |
|--------|-------|
| **Passed** | **784 / 1500 (52.3%)** |
| Failed | 716 |
| Unverified | 0 |
| Selected for SFT | 256 (784 passes available; `--max-per-task 10`) |

| Task type | Pass rate |
|-----------|-----------|
| `typescript_bugfix` | 327/400 (**81.8%**) |
| `typescript_refactor` | 189/300 (**63.0%**) |
| `react_component` | 162/400 (40.5%) |
| `zod_schema` | 106/400 (26.5%) |

| Tier | Pass rate |
|------|-----------|
| `proven` | 446/750 (59.5%) |
| `revised` | 328/600 (54.7%) |
| `baseline` | 10/150 (**6.7%**) — regression anchors; do not use for SFT mix |

**Top failure checks:** `node:vitest` (666), `typescript:tsc` (303).

**Weakest tasks (0–12%):** `expanded_zod_schema_003` (0/50), `nr_zod_schema_001` (0/50), `expanded_react_component_002` (1/50), `nr_ts_refactor_003` (3/50), `expanded_zod_schema_005` (6/50).

**Strongest tasks (94–100%):** `expanded_refactor_001`, `expanded_ts_bugfix_001` (50/50); several bugfix/refactor tasks ≥92%.

Compare: mixed-language full distill **40.9%**; calibration on this track **46%**; full TS 30×50 **52.3%**.

### Calibration (reference)

10 tasks × 5 = 50 samples — **23/50 (46%)** after harness fixes. Artifacts: `calibrate_10x5.jsonl`, `calibrate_10x5.verified.jsonl`, [`calibrate_10x5.analysis.txt`](phase2/outputs/calibrate_10x5.analysis.txt).

### Verifier harness (implemented)

| Fix | Effect |
|-----|--------|
| `vitest.setup.ts` + jest-dom | React harness; major calibration gain |
| `strip_markdown_fences()` | Strips ` ```typescript ` wrappers from test turns |

### Open (next iteration)

- **Prompt curation:** drop or rewrite `baseline` tier tasks; replace 0% Zod tasks (`expanded_zod_schema_003`, `nr_zod_schema_001`).
- **`TEST_SYSTEM_PROMPT`:** Zod 4 `.issues`, reject-vs-clamp, shorter tests; React async/timer guidance.
- **Verifier (optional):** unused `@ts-expect-error`, truncation detection / `MAX_TOKENS_TESTS`.
- **Larger SFT export:** re-run `select_passed.py` with higher `--max-per-task` or export all 784 passes if needed.
- **Phase 3** student baseline (parent PLAN).

## Next actions

1. Use **`solution_sft.jsonl`** (256 rows) for prototype student SFT, or re-select with a higher per-task cap.
2. Build **`typescript_tasks_30_v2.jsonl`**: remove/replace baseline + 0% tasks; keep proven/revised winners.
3. Tune **`TEST_SYSTEM_PROMPT`** and category templates; re-calibrate (~50) before another 1500 run.
4. Phase 3 student baseline (see [`deploy/distill/PLAN.md`](../distill/PLAN.md)).

## Scripts

| Script | Purpose |
|--------|---------|
| [`run_calibrate.sh`](run_calibrate.sh) | 50-sample gen → verify → analyze |
| [`run_pipeline.sh`](run_pipeline.sh) | Full gen → verify → select |
| [`phase1/analyze_pass_rates.py`](phase1/analyze_pass_rates.py) | Per-task pass-rate report |

Phase 0: reuse [`deploy/distill/phase0/`](../distill/phase0/).
