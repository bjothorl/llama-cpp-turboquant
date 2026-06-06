# Phase 2 — Verify and select (no repair)

## Setup

```bash
cp deploy/distill_no-repair/phase2/verifier.env.example deploy/distill_no-repair/phase2/verifier.env
```

Set `INSTALL_NODE_DEPS=true` for real Vitest and `tsc` checks.

## Verify

```bash
python3 deploy/distill_no-repair/phase2/verify_samples.py --install-node-deps
```

## Analyze

```bash
python3 deploy/distill_no-repair/phase1/analyze_pass_rates.py \
  --input deploy/distill_no-repair/phase2/outputs/calibrate_10x5.verified.jsonl
```

## Select passed rows for SFT

```bash
python3 deploy/distill_no-repair/phase2/select_passed.py \
  --input deploy/distill_no-repair/phase2/outputs/calibrate_10x5.verified.jsonl \
  --output deploy/distill_no-repair/phase2/outputs/calibrate.solution_sft.jsonl \
  --max-per-task 10
```

Workdirs: `outputs/work/<sample-id>/`. Shared deps: `outputs/node_sandbox/`.
