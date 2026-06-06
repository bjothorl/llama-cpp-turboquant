# Phase 2 Verification Pilot

Phase 2 verifies raw Phase 1 samples and writes a derived JSONL with verification results. It does not mutate the raw corpus.

## Files

- `verifier.env.example` - default input, output, workdir, and timeout settings.
- `verify_samples.py` - materializes samples and runs language checks.
- `select_solution_sft.py` - selects verified passing candidates and emits weak-group repair IDs.
- `repair_failures.py` - builds deterministic repair prompts from failed verifier output and writes repaired JSONL.
- `write_repaired_ids.py` - writes an ID file for rows touched by a repair batch.
- `export_repair_sft.py` - exports successful verified repairs as a repair/review SFT dataset.
- `outputs/` - derived verification artifacts, ignored by git.
- `outputs/node_sandbox/` - shared Node dependencies when `INSTALL_NODE_DEPS=true`.

## Setup

```bash
cp deploy/distill/phase2/verifier.env.example deploy/distill/phase2/verifier.env
```

## Run Verification

```bash
python3 deploy/distill/phase2/verify_samples.py
```

Default input:

```text
deploy/distill/phase1/outputs/pilot.jsonl
```

Default output:

```text
deploy/distill/phase2/outputs/pilot.verified.jsonl
deploy/distill/phase2/outputs/pilot.verified.summary.json
```

## What It Checks

Python:

- Writes `solution.py` and `test_solution.py`.
- Normalizes `from .solution import ...` to `from solution import ...`.
- Adds `from solution import *` when tests assume the implementation is in scope.
- Runs `py_compile` on solution and tests.
- Runs `pytest` when available, otherwise `unittest discover`.

TypeScript/JavaScript:

- Writes `solution.ts`/`solution.js` and `solution.test.ts`/`solution.test.js`.
- Writes a minimal `package.json` describing detected dev dependencies.
- Runs `node --check` for JavaScript.
- Runs `npx --no-install tsc --noEmit` for TypeScript when `npx` and local/cached `tsc` are available.
- Runs detected test runner with `npx --no-install` when available. Generic `describe`/`it`/`test`/`expect` tests default to Vitest so JavaScript samples do not pass on syntax alone.

No dependencies are installed automatically. Missing Node tools/packages are reported as skipped checks, and samples with only skipped checks are marked `unverified` rather than `failed`. A sample is `failed` only when at least one check actually ran and failed.

To run full Node/TypeScript checks, enable dependency installation:

```bash
python3 deploy/distill/phase2/verify_samples.py --install-node-deps
```

or set this in `deploy/distill/phase2/verifier.env`:

```bash
INSTALL_NODE_DEPS=true
```

This runs `npm install --no-audit --no-fund` once inside the shared `NODE_SANDBOX` directory, then symlinks its `node_modules` into each generated work directory before `tsc`, `vitest`, or `jest`. Use this only in a sandboxed environment you are comfortable executing generated code in.

## Inspect Failures

Work directories are kept by default:

```text
deploy/distill/phase2/outputs/work/<sample-id>/
```

Each contains:

- `sample.json`
- `solution.*`
- `solution.test.*`
- `package.json` for Node samples

Use these files to debug prompt or extraction failures.

## Select Solution SFT

After verifying a multi-candidate file, select passing candidates for solution SFT:

```bash
python3 deploy/distill/phase2/select_solution_sft.py \
  --input deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.verified.jsonl \
  --output deploy/distill/phase2/outputs/solution_sft.seed_50x.max10.jsonl \
  --max-per-task 10 \
  --min-passing-per-task 10
```

This writes:

```text
deploy/distill/phase2/outputs/solution_sft.seed_50x.max10.jsonl
deploy/distill/phase2/outputs/solution_sft.seed_50x.max10.manifest.json
deploy/distill/phase2/outputs/solution_sft.seed_50x.max10.weak_failed_ids.txt
```

Use the weak ID file to target repairs only at groups that did not produce enough passing candidates.

## Repair Failed Samples

After verification, repair failed samples without mutating the original JSONL:

```bash
python3 deploy/distill/phase2/repair_failures.py --dry-run
python3 deploy/distill/phase2/repair_failures.py
```

Default input:

```text
deploy/distill/phase2/outputs/pilot.verified.jsonl
```

Default output:

```text
deploy/distill/phase2/outputs/pilot.repaired.jsonl
```

The repair prompt is generated mechanically from:

- original task
- current solution
- current tests
- failing verifier stdout/stderr

The teacher must return strict JSON with a failure classification and either replacement solution code, replacement test code, or no repair for harness/underspecified cases. Repair attempts are stored in `meta.repair_attempts`.

For large files, repair in chunks instead of sending every failure to the teacher:

```bash
python3 deploy/distill/phase2/repair_failures.py \
  --input deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.verified.jsonl \
  --output deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.repaired.batch001.jsonl \
  --max-repairs 100
```

Continue with an offset:

```bash
python3 deploy/distill/phase2/repair_failures.py \
  --input deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.verified.jsonl \
  --output deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.repaired.batch002.jsonl \
  --offset 100 \
  --max-repairs 100
```

You can also pass `--ids-file path/to/ids.txt` to repair only selected sample IDs.

For example, repair only failed candidates from weak groups:

```bash
python3 deploy/distill/phase2/repair_failures.py \
  --input deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.verified.jsonl \
  --output deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.weak_repaired.jsonl \
  --ids-file deploy/distill/phase2/outputs/solution_sft.seed_50x.max10.weak_failed_ids.txt \
  --max-repairs 100
```

Write an ID file for only the rows touched by that repair batch:

```bash
python3 deploy/distill/phase2/write_repaired_ids.py \
  --input deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.weak_repaired.batch001.jsonl \
  --output deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.weak_repaired.batch001.ids.txt
```

Then verify only those repaired rows:

```bash
python3 deploy/distill/phase2/verify_samples.py \
  --input deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.weak_repaired.batch001.jsonl \
  --output deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.weak_repaired.batch001.repaired_only.verified.jsonl \
  --ids-file deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.weak_repaired.batch001.ids.txt
```

Re-verify repaired output:

```bash
python3 deploy/distill/phase2/verify_samples.py \
  --input deploy/distill/phase2/outputs/pilot.repaired.jsonl \
  --output deploy/distill/phase2/outputs/pilot.repaired.verified.jsonl
```

## Export Repair SFT

After a repaired file has been re-verified, export successful repairs into a separate review/repair dataset:

```bash
python3 deploy/distill/phase2/export_repair_sft.py \
  --input deploy/distill/phase2/outputs/expanded_pilot.repaired.v4.verified.jsonl \
  --output deploy/distill/phase2/outputs/repair_sft.jsonl
```

The exporter includes only samples that:

- have at least one repair attempt with original broken code/tests recorded
- changed either solution or tests
- passed verification after repair

The output trains a review agent shape: task, broken solution/tests, verifier failure log, then strict JSON containing `failure_cause`, `repair_target`, and the corrected code or tests.

## Verify The Expanded Pilot

After generating `deploy/distill/phase1/outputs/expanded_pilot.jsonl`, keep derived artifacts separate:

```bash
python3 deploy/distill/phase2/verify_samples.py \
  --input deploy/distill/phase1/outputs/expanded_pilot.jsonl \
  --output deploy/distill/phase2/outputs/expanded_pilot.verified.jsonl
```

Repair and re-verify:

```bash
python3 deploy/distill/phase2/repair_failures.py \
  --input deploy/distill/phase2/outputs/expanded_pilot.verified.jsonl \
  --output deploy/distill/phase2/outputs/expanded_pilot.repaired.jsonl

python3 deploy/distill/phase2/verify_samples.py \
  --input deploy/distill/phase2/outputs/expanded_pilot.repaired.jsonl \
  --output deploy/distill/phase2/outputs/expanded_pilot.repaired.verified.jsonl
```
