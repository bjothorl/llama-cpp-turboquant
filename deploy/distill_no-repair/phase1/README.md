# Phase 1 — Generate TypeScript samples

Two-turn generation against local `llama-server` `/v1/chat/completions`:

1. Solution code
2. Tests for that solution

## Setup

```bash
cp deploy/distill_no-repair/phase1/generator.env.example deploy/distill_no-repair/phase1/generator.env
```

## Commands

```bash
python3 deploy/distill_no-repair/phase1/generate_samples.py --dry-run

python3 deploy/distill_no-repair/phase1/generate_samples.py \
  --prompts deploy/distill_no-repair/phase1/prompts/typescript_tasks_calibrate.jsonl \
  --output deploy/distill_no-repair/phase1/outputs/calibrate_10x5.jsonl \
  --max-samples 10 \
  --candidates 5
```

Test-turn instructions are in `TEST_SYSTEM_PROMPT` inside [`generate_samples.py`](generate_samples.py) (see [`prompts/PROMPT_DESIGN.md`](prompts/PROMPT_DESIGN.md)).

## Prompt files

Regenerate from expanded pilot:

```bash
python3 deploy/distill_no-repair/phase1/build_prompts.py
```
