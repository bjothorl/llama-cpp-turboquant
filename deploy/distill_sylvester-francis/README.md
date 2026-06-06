# distill_sylvester-francis — step-by-step

Train a TypeScript LoRA on `Qwen/Qwen3.5-9B` using data from [sylvester-francis/slm-typescript-model](https://github.com/sylvester-francis/slm-typescript-model), convert back to MTP-capable GGUF, and serve through `llama-server --spec-type draft-mtp`.

Goals, constraints, recipe: [`PLAN.md`](PLAN.md).

## Prerequisites

From the repo root (`/home/b/repos/llama-cpp-turboquant`):

- Built `llama-server` and `convert_hf_to_gguf.py` available (already in this repo)
- Python **3.10+**, with `venv` available
- CUDA-capable GPU; this stack targets RTX 3090 (24 GB)
- A `GITHUB_TOKEN` if Sylvester's `collect` step needs to scrape GitHub (skip if you grab his pre-processed JSONL via HF)
- `HF_TOKEN` is **not** required — `Qwen/Qwen3.5-9B` and `unsloth/Qwen3.5-9B-MTP-GGUF` are un-gated
- ~60 GB free disk during the smoke run (base weights + merged + GGUF intermediates)

## One-time setup

```bash
cp deploy/distill_sylvester-francis/.env.example deploy/distill_sylvester-francis/.env
cp deploy/distill_sylvester-francis/phase2_train/train.env.example deploy/distill_sylvester-francis/phase2_train/train.env
# edit .env to set HF_TOKEN, paths, etc.
```

Create the training virtualenv (separate from your system Python so CUDA wheels are isolated):

```bash
python3 -m venv ~/.venvs/distill-sf
source ~/.venvs/distill-sf/bin/activate
pip install --upgrade pip
pip install -r deploy/distill_sylvester-francis/requirements.txt
```

> The first install pulls ~3 GB of CUDA wheels (torch + bitsandbytes). Run it manually so you can monitor.

## Phase 1 — Fetch Sylvester's data

```bash
deploy/distill_sylvester-francis/phase1_data/fetch_sylvester.sh
```

This clones `slm-typescript-model` to `~/slm-typescript-model`, runs his `preprocess` step, and links the resulting JSONL into `deploy/distill_sylvester-francis/data/`. If you have a `GITHUB_TOKEN` and want the full collect, pass `--collect` to the script.

Inspect what arrived:

```bash
python3 deploy/distill_sylvester-francis/phase1_data/inspect_data.py \
  --input deploy/distill_sylvester-francis/data/train_small.jsonl
```

Reports row count, text length p50/p95, source distribution, and the first 3 rows. Use this to sanity-check shape before training.

## Phase 2 — QLoRA train (smoke first)

Smoke run (100 rows, 1 epoch):

```bash
deploy/distill_sylvester-francis/phase2_train/train_qlora.py \
  --data deploy/distill_sylvester-francis/data/train_small.jsonl \
  --max-samples 100 \
  --output adapters/qwen35-9b-ts-smoke \
  --epochs 1
```

The script reads defaults from `phase2_train/train.env`. Expect 15–25 min on a 3090, peak VRAM ~14 GB.

Full run (later, after the smoke is green):

```bash
deploy/distill_sylvester-francis/phase2_train/train_qlora.py \
  --data deploy/distill_sylvester-francis/data/train_medium.jsonl \
  --output adapters/qwen35-9b-ts-full \
  --epochs 2
```

## Phase 3 — Merge + convert to GGUF (with MTP)

```bash
deploy/distill_sylvester-francis/phase3_convert/merge_adapter.py \
  --base Qwen/Qwen3.5-9B \
  --adapter adapters/qwen35-9b-ts-smoke \
  --output models/qwen35-9b-ts-smoke-merged

deploy/distill_sylvester-francis/phase3_convert/convert_to_gguf.sh \
  --src models/qwen35-9b-ts-smoke-merged \
  --out models/qwen35-9b-ts-smoke.Q4_K_M.gguf \
  --quant Q4_K_M
```

`convert_to_gguf.sh` invokes this repo's `convert_hf_to_gguf.py` (without `--mtp` — the default path preserves NextN tensors for `Qwen3_5TextModel` / `Qwen3_5MoeTextModel`; `--mtp` would produce a draft-only submodel), then runs `build/bin/llama-quantize` for the requested type. Final GGUF should report `nextn_predict_layers > 0` in its metadata.

## Phase 4 — Measure MTP acceptance + sanity outputs

Baseline (untrained `unsloth/Qwen3.5-9B-MTP-GGUF`):

```bash
deploy/distill_sylvester-francis/phase4_eval/serve_baseline.sh
# in another shell or after it's ready:
python3 deploy/distill_sylvester-francis/phase4_eval/measure_mtp.py \
  --label baseline \
  --prompts deploy/distill/phase0/prompts/smoke-10.jsonl
```

Stop the baseline server, then trained:

```bash
deploy/distill_sylvester-francis/phase4_eval/serve_trained.sh \
  --model models/qwen35-9b-ts-smoke.Q4_K_M.gguf

python3 deploy/distill_sylvester-francis/phase4_eval/measure_mtp.py \
  --label trained \
  --prompts deploy/distill/phase0/prompts/smoke-10.jsonl
```

Compare:

```bash
python3 deploy/distill_sylvester-francis/phase4_eval/compare.py \
  --baseline deploy/distill_sylvester-francis/phase4_eval/runs/baseline/smoke_summary.json \
  --trained  deploy/distill_sylvester-francis/phase4_eval/runs/trained/smoke_summary.json
```

Gate: trained MTP acceptance must be **≥ 80%** of baseline, per [`PLAN.md`](PLAN.md).

## Artifact map

```text
deploy/distill_sylvester-francis/
  PLAN.md
  README.md
  requirements.txt
  .env.example
  phase1_data/
    fetch_sylvester.sh
    inspect_data.py
  phase2_train/
    train_qlora.py
    train.env.example
  phase3_convert/
    merge_adapter.py
    convert_to_gguf.sh
  phase4_eval/
    serve_baseline.sh
    serve_trained.sh
    measure_mtp.py
    compare.py
  data/         (gitignored)  Sylvester JSONL
  adapters/     (gitignored)  trained LoRA
  models/       (gitignored)  merged HF + GGUF
  phase4_eval/runs/   (gitignored)  server logs + smoke outputs
```
