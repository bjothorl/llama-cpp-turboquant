# distill_sylvester-francis — TS LoRA on Qwen3.5-9B-MTP

Experimental track: train a TypeScript LoRA on `Qwen/Qwen3.5-9B` (HF safetensors of the same family as `unsloth/Qwen3.5-9B-MTP-GGUF`) using data produced by [sylvester-francis/slm-typescript-model](https://github.com/sylvester-francis/slm-typescript-model), then convert back to MTP-capable GGUF and serve through `llama-server --spec-type draft-mtp`.

Full roadmap and constraints: [`deploy/distill/PLAN.md`](../distill/PLAN.md).

## Why this track

- **Data:** `distill/` and `distill_no-repair/` produce ~10² verified rows per pipeline run. Sylvester's stack ships **~5k–8k** TS samples from popular GitHub repos. Larger surface, different distribution.
- **Method comparison:** continued-pretraining-style data (raw code + Q&A) instead of chat SFT — a different lever than synthetic teacher generation.
- **Same student family:** keeps the MTP runtime contract from `PLAN.md` (Phase 4.5).

## Non-negotiable constraints (inherited from `distill/PLAN.md`)

1. **MTP must survive the round-trip.** Base ships with NextN/MTP tensors; conversion must preserve `nextn_predict_layers > 0`; draft acceptance must stay above 80% of the untuned baseline.
2. **No claim of release-bound provenance.** Sylvester's data is scraped from public GitHub. Treat outputs of this track as **private/local-use** until licensing is reviewed.
3. **Measure before declaring success.** Compare base vs. trained on the same `llama-server` build, same quant, same prompts.

## Hardware target

- RTX 3090 (24 GB), 61 GB RAM, ~1.6 TB free disk.
- 9B HF base in bf16 ≈ 18 GB → does **not** fit with optimizer + activations.
- **QLoRA (4-bit base via bitsandbytes, bf16 LoRA adapters)** is the only realistic recipe on this box.

## Training recipe (recommended starting point)

| Knob | Value | Rationale |
|------|-------|-----------|
| Base | `Qwen/Qwen3.5-9B` | HF safetensors; same family as `unsloth/Qwen3.5-9B-MTP-GGUF` |
| Quant | `bnb-4bit` nf4 + double quant | Fits 9B in <12 GB |
| LoRA rank / α | **r=16, α=32** | Lower than Sylvester's r=64 — reduces main-distribution shift to protect MTP acceptance (PLAN.md Phase 4.5 lever) |
| LoRA dropout | 0.05 | |
| Targets | `all-linear` (PEFT auto-discover) | Qwen3.5 uses Gated DeltaNet; module names differ from Qwen2.5 |
| Max seq length | 1024 (smoke) → 2048 (full) | Fits with QLoRA + gradient checkpointing |
| Batch / grad-accum | 1 / 16 (eff. 16) | |
| Optimizer | `paged_adamw_8bit` | bnb-friendly |
| LR / schedule | 1e-4 cosine, 3% warmup | Conservative vs. Sylvester's 2e-4 (instruct model + MTP) |
| Precision | bf16 compute | 3090 supports bf16 |
| Packing | off | Avoid mixing unrelated TS files in one sequence |
| Epochs | 1 (smoke) → 2 (full) | Over-training risks chat / thinking regression |
| Data (smoke) | 100 rows of `train_small.jsonl` | ~15–25 min on 3090 |
| Data (full) | `train_medium.jsonl` (~5k) | ~6–10 h on 3090 |

## Risks acknowledged

| # | Risk | Mitigation in this track |
|---|------|-------------------------|
| 1 | MTP draft acceptance collapse | Low rank, `all-linear` targets, measure pre/post in `phase4_eval` |
| 2 | Data shape mismatch (continued-pretraining vs. chat SFT) | Smoke test outputs on coding prompts; abort if chat coherence breaks |
| 3 | Arch differences (Qwen3.5 Gated DeltaNet vs. Qwen2.5 stock) | `all-linear` LoRA targets; verify via `model.print_trainable_parameters()` |
| 4 | VRAM | QLoRA 4-bit; bs=1 ga=16; gradient checkpointing |
| 5 | GGUF conversion preserving MTP | Use this repo's `convert_hf_to_gguf.py` (default path; `Qwen3_5TextModel` and `Qwen3_5MoeTextModel` both inherit `_Qwen35MtpMixin` and emit `nextn_predict_layers`). Do **not** pass `--mtp` — that produces a draft-only submodel. |
| 6 | Data license / provenance | Track-level note; do not redistribute outputs without review |

## Exit criteria

A smoke run is **green** when all of these hold:

- ✓ Training completes without OOM on the 3090
- ✓ Merge + convert produces a GGUF whose metadata shows `nextn_predict_layers > 0`
- ✓ `llama-server --spec-type draft-mtp` starts on the new GGUF
- ✓ MTP draft acceptance on `deploy/distill/phase0/prompts/smoke-10.jsonl` is **≥ 80% of the untrained `Qwen3.5-9B-MTP-GGUF` baseline**
- ✓ Outputs are coherent TypeScript, not garbage / chat regression

If acceptance drops below the gate already at r=16, that itself is a useful finding — record it and decide whether to lower rank further, switch to chat-formatted SFT, or accept this as a non-MTP TS adapter.

## Phases

```text
phase1_data/      clone sylvester repo + run his collect/preprocess → JSONL
phase2_train/     QLoRA on Qwen/Qwen3.5-9B
phase3_convert/   merge adapter → safetensors fp16 → GGUF (--mtp)
phase4_eval/      serve base & trained; measure MTP accept + tok/s + smoke outputs
```

See [`README.md`](README.md) for the step-by-step commands.
