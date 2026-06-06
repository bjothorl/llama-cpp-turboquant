# Phase 1 Dataset Pilot

Phase 1 starts the raw synthetic dataset pipeline. It calls a local OpenAI-compatible `llama-server` teacher, asks each seed task for a solution, asks a second turn for tests, then appends structured JSONL.

## Files

- `generator.env.example` - default local server and generation settings.
- `prompts/pilot_tasks.jsonl` - five seed tasks for the first pilot corpus.
- `prompts/expanded_pilot_tasks.jsonl` - 30 balanced tasks for the next pilot run.
- `generate_samples.py` - two-turn sample generator.
- `extract_sample.py` - response parsing helpers for reasoning, code fences, and tests.
- `schemas/sample.schema.json` - expected JSONL sample shape.
- `outputs/` - generated JSONL artifacts, ignored by git.

## Setup

Start your teacher server first. For the 35B teacher, the existing service is:

```bash
systemctl --user start llama-turbo-server.service
curl -fsS http://127.0.0.1:8080/health
```

Copy defaults:

```bash
cp deploy/distill/phase1/generator.env.example deploy/distill/phase1/generator.env
```

If `LLAMA_API_KEY` is already exported globally, no local env edit is needed. If not, add it to `generator.env` and do not commit that file.

## Dry Run

Validate settings without calling the model:

```bash
python3 deploy/distill/phase1/generate_samples.py --dry-run
```

## Generate The 5-Sample Pilot

```bash
python3 deploy/distill/phase1/generate_samples.py
```

Default output:

```text
deploy/distill/phase1/outputs/pilot.jsonl
```

This file is append-only. Delete or move it manually if you want a fresh pilot run.

By default the generator sends `chat_template_kwargs.enable_thinking=false`. This is important when the teacher server was started with reasoning enabled; otherwise Qwen may spend the whole token budget in `reasoning_content` and return empty `content`.

## Generate The 30-Task Expanded Pilot

Keep this output separate from the five-sample pilot:

```bash
python3 deploy/distill/phase1/generate_samples.py \
  --prompts deploy/distill/phase1/prompts/expanded_pilot_tasks.jsonl \
  --output deploy/distill/phase1/outputs/expanded_pilot.jsonl \
  --max-samples 30
```

Default categories in the expanded prompt file:

- TypeScript bug fixes
- Python implementations
- React components
- JavaScript debugging tasks
- Zod schemas
- TypeScript/Python refactors

## Generate Multiple Candidates

Use `--candidates` to generate best-of-N raw data without duplicating sample IDs. For example, 30 prompts with 10 candidates produces 300 raw samples:

```bash
python3 deploy/distill/phase1/generate_samples.py \
  --prompts deploy/distill/phase1/prompts/expanded_pilot_tasks.jsonl \
  --output deploy/distill/phase1/outputs/expanded_pilot_candidates_10x.jsonl \
  --max-samples 30 \
  --candidates 10
```

Candidate sample IDs are suffixed with `_cNN`, and each sample records `source_task_id`, `candidate`, and `candidates_per_task` in `meta`.

## Inspect Output

```bash
python3 - <<'PY'
import json
from pathlib import Path
path = Path("deploy/distill/phase1/outputs/pilot.jsonl")
for line in path.read_text().splitlines():
    row = json.loads(line)
    print(row["id"], "code_chars=", len(row["code"]), "tests_chars=", len(row["tests"]))
PY
```

## Current Limitations

- Compile/test verification is handled by Phase 2. `verification` fields in raw Phase 1 output are placeholders.
- Code/test extraction is heuristic and keeps raw responses for later repair.
- Best-of-N selection is not implemented yet; `--candidates` generates multiple raw candidates, but selection still happens manually through Phase 2 verification outputs.
