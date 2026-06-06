# distill_no-repair — TypeScript verify-only pipeline

Prototype track for local coding distillation: generate code + tests from the 35B teacher, verify with `tsc` and Vitest, export passing rows for SFT. **No repair step.**

Full roadmap and execution history: [`deploy/distill/PLAN.md`](../distill/PLAN.md).

## Prerequisites

From the repository root:

- Built `llama-server` and a running teacher (e.g. `systemctl --user start llama-turbo-server.service`)
- `curl -fsS http://127.0.0.1:8080/health`
- Python 3
- Node.js + npm (for real TypeScript verification)
- `LLAMA_API_KEY` in the environment (or in local `*.env` files — never commit keys)

```bash
cd /home/b/repos/llama-cpp-turboquant
cp deploy/distill_no-repair/phase1/generator.env.example deploy/distill_no-repair/phase1/generator.env
cp deploy/distill_no-repair/phase2/verifier.env.example deploy/distill_no-repair/phase2/verifier.env
```

Phase 0 baseline tools are shared: [`deploy/distill/phase0/README.md`](../distill/phase0/README.md).

## Quick start (smoke)

```bash
python3 deploy/distill_no-repair/phase1/generate_samples.py --dry-run

python3 deploy/distill_no-repair/phase1/generate_samples.py

python3 deploy/distill_no-repair/phase2/verify_samples.py --install-node-deps

python3 deploy/distill_no-repair/phase2/select_passed.py \
  --input deploy/distill_no-repair/phase2/outputs/pilot.verified.jsonl \
  --output deploy/distill_no-repair/phase2/outputs/pilot.solution_sft.jsonl
```

## Calibration (~50 samples)

Validate prompt curation before a long run:

```bash
chmod +x deploy/distill_no-repair/run_calibrate.sh
./deploy/distill_no-repair/run_calibrate.sh
```

Produces:

- `phase1/outputs/calibrate_10x5.jsonl`
- `phase2/outputs/calibrate_10x5.verified.jsonl`
- `phase2/outputs/calibrate_10x5.analysis.txt`

Gate: if pass rate is below ~35%, adjust category templates in [`phase1/prompts/PROMPT_DESIGN.md`](phase1/prompts/PROMPT_DESIGN.md) — not individual task IDs.

## Full run (1500 samples)

```bash
chmod +x deploy/distill_no-repair/run_pipeline.sh
./deploy/distill_no-repair/run_pipeline.sh
```

Default: 30 tasks × 50 candidates from `typescript_tasks_30.jsonl`.

**Completed run (2026-05-25):** 784/1500 passed (**52.3%**); **256** rows in `phase2/outputs/solution_sft.jsonl` (`--max-per-task 10`). See [`PLAN.md`](PLAN.md).

### 900-sample baseline (18 tasks)

```bash
PROMPTS_FILE=deploy/distill_no-repair/phase1/prompts/typescript_tasks.jsonl \
MAX_SAMPLES=18 \
RAW_OUTPUT=deploy/distill_no-repair/phase1/outputs/typescript_18x50.jsonl \
VERIFIED_OUTPUT=deploy/distill_no-repair/phase2/outputs/typescript_18x50.verified.jsonl \
./deploy/distill_no-repair/run_pipeline.sh
```

## Artifact map

```text
deploy/distill_no-repair/
  PLAN.md
  README.md
  run_calibrate.sh
  run_pipeline.sh
  phase1/prompts/          task JSONL + PROMPT_DESIGN.md
  phase1/outputs/          raw generated JSONL (gitignored)
  phase2/outputs/          verified JSONL, workdirs, node_sandbox
  phase2/outputs/solution_sft.jsonl   training export (passed only)
```

## Scripts

| Script | Role |
|--------|------|
| `phase1/generate_samples.py` | Two-turn teacher generation |
| `phase1/analyze_pass_rates.py` | Per-task pass-rate report |
| `phase2/verify_samples.py` | Materialize + run tsc/Vitest |
| `phase2/select_passed.py` | Export verified passes for SFT |
| `phase1/build_prompts.py` | Regenerate prompt JSONL from expanded pilot |

## Compare with existing 50× TS data

Filter TypeScript rows from the full distill verify output without regenerating:

```bash
python3 -c "
import json, sys
for line in open('deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.verified.jsonl'):
    r = json.loads(line)
    if r.get('language') == 'typescript':
        sys.stdout.write(line)
" > deploy/distill_no-repair/phase2/outputs/imported_ts_50x.verified.jsonl

python3 deploy/distill_no-repair/phase1/analyze_pass_rates.py \
  --input deploy/distill_no-repair/phase2/outputs/imported_ts_50x.verified.jsonl
```

## What this omits

Repair loop scripts from [`deploy/distill/phase2/`](../distill/phase2/) (`repair_failures.py`, `export_repair_sft.py`, etc.). Use the full distill tree when repair SFT is needed.
