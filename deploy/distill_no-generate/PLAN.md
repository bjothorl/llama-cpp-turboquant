# Downloaded-data SFT (no local generation)

Simpler track than [`deploy/distill_no-repair/`](../distill_no-repair/) and [`deploy/distill/`](../distill/): skip teacher generation entirely. Pull license-clean prompt+answer pairs from public datasets, normalize to our JSONL schema, optionally re-verify a sample with the existing harness, feed to SFT.

## Why this exists

The local-generation tracks produce on the order of 10² SFT rows per full pipeline run (`distill_no-repair/`: 256 rows from a 30×50 run at 52.3% first-pass verify). Open instruct-code datasets are 10²–10³× larger and already filtered, with stronger coverage of categories where the local teacher caps out (Zod, async React: 0–7%). Use them where licensing permits. Fall back to [`distill/`](../distill/) or [`distill_no-repair/`](../distill_no-repair/) only for user-codebase-specific tasks the public data does not cover.

## Scope

- **No teacher generation.** `llama-server` is not required for the data path.
- **Normalize, don't regenerate.** Map source records to the schema in [`deploy/distill/PLAN.md`](../distill/PLAN.md#phase-1---build-synthetic-dataset-pipeline).
- **Re-verification is optional and sampled.** Reuse [`distill_no-repair/phase2/verify_samples.py`](../distill_no-repair/phase2/verify_samples.py) as a harness sanity check, not as the primary filter.
- **MTP preservation is a training-recipe concern**, not a data-sourcing one. Same gate as the parent PLAN.

## Candidate datasets

License must be verified per-dataset against the parent PLAN's [non-negotiable constraints](../distill/PLAN.md#use-only-permitted-training-data) before any row enters the SFT mix. Sizes are approximate; pin a commit hash before use.

| Dataset | HF id | Approx size | Status | Notes |
|---|---|---:|---|---|
| KodCode v1 SFT | `KodCode/KodCode-V1-SFT-4o` | ~268k | Allowed by parent PLAN | Multi-language; GPT-4o-derived solutions; confirm current dataset card terms |
| OpenCoder SFT stage 1 | `OpenCoder-LLM/opc-sft-stage1` | ~4M | License check pending | Broad coverage; check downstream-use clause |
| OpenCoder SFT stage 2 | `OpenCoder-LLM/opc-sft-stage2` | ~430k | License check pending | Smaller, higher-signal subset |
| OpenCodeInstruct | `nvidia/OpenCodeInstruct` | ~1.5M | License check pending | Confirm CC-BY scope and any non-compete clause |
| Magicoder OSS-Instruct | `ise-uiuc/Magicoder-OSS-Instruct-75K` | ~75k | Quarantine pending vet | Generated via GPT-3.5; check current OpenAI ToU re: competing-model training |
| CodeFeedback-Filtered | `m-a-p/CodeFeedback-Filtered-Instruction` | ~157k | Quarantine pending vet | Mixed upstream sources |
| The Stack v2 (smol) | `bigcode/the-stack-v2-train-smol-ids` | raw code | Defer | Not instruct; would need pairing |

Quarantined unconditionally (parent PLAN): anything advertised as Claude/Opus/Gemini-derived without explicit redistribution and training rights.

## Target schema

Identical to [`deploy/distill/PLAN.md`](../distill/PLAN.md#jsonl-schema), with these field conventions:

- `source.kind` = `huggingface` (instead of `synthetic_template`).
- `source.license` = the verified upstream license string; never `local`.
- `source.uri` = `https://huggingface.co/datasets/<id>` plus revision/commit hash.
- `meta.teacher` = `null` (no local teacher).
- `meta.upstream` = `{ dataset_id, revision, row_index, original_id? }`.
- `verification.phase2` = present only on the re-verified sample subset.

## Workflow

1. **Phase 1 — download + normalize.**
   - `phase1/download.py <dataset_id> --revision <sha> --out cache/<dataset_id>/`
   - `phase1/normalize.py <cache> --out outputs/<dataset_id>.jsonl` (one schema map per dataset).
   - `phase1/filter.py` — language allowlist, length caps, near-duplicate hashing, drop rows whose prompts/solutions appear byte-for-byte in held-out evals (HumanEval, MBPP, LiveCodeBench, BigCodeBench).
2. **Phase 2 — sampled re-verification (optional).**
   - Draw ~500 rows per dataset stratified by `task_type`.
   - Run [`distill_no-repair/phase2/verify_samples.py`](../distill_no-repair/phase2/verify_samples.py) with `INSTALL_NODE_DEPS=true`.
   - Investigate the upstream pipeline if pass rate is far below the dataset card's claim. Do not use this to discard individual rows — these datasets are already filtered.
3. **Phase 3+** — student baseline, LoRA training, MTP acceptance gate. See parent PLAN.

## Mixture (initial proposal)

Tune after the first student baseline.

| Source | Share | Rationale |
|---|---:|---|
| KodCode v1 SFT, filtered to TS + Python | 60% | Already allowed; verified; matches target languages |
| OpenCoder stage 2 (after license check) | 25% | High-signal subset; diversifies away from any single teacher |
| `distill_no-repair/` passes | 10% | Keeps a small user-codebase-style slice in the mix |
| Reasoning-on subset (separate adapter) | 5% | Train as a separate adapter; do not mix into the reasoning-off run |

## Open questions

- **Benchmark leakage.** Enforce dedup against HumanEval, MBPP, LiveCodeBench, BigCodeBench before any training run. Treat any match as a hard drop.
- **Reasoning traces.** Most public sets do not have `<think>` traces; keep `reasoning` empty rather than fabricating one.
- **Dataset card drift.** Pin a commit hash per dataset and re-check the license string at pin time, not at pull time.
- **Cross-track dedup.** Strip exact matches between `distill_no-repair/` outputs and downloaded rows so the small local slice does not get drowned by near-duplicates.

## Trade-offs vs. local generation

- No alignment with the local teacher's exact chat template or answer style. Probably fine for SFT; may need a small style-alignment slice later.
- Less per-row control. Trust upstream filtering quality.
- Public benchmark contamination risk is real and requires explicit dedup; local-gen avoids this by construction.

## Scripts (to write)

| Path | Purpose |
|---|---|
| `phase1/download.py` | HF dataset pull with pinned revision |
| `phase1/normalize.py` | Source-specific schema map |
| `phase1/filter.py` | Lang / length / dedup / benchmark-leakage filters |
| `phase2/verify_subset.py` | Stratified sampling wrapper over the existing verifier |
| `phase2/export_sft.py` | Export filtered rows to `solution_sft.jsonl` |
| [`run_pilot.sh`](run_pilot.sh) | 1 shard, 1000 rows, verify 50 |
| [`run_full.sh`](run_full.sh) | All 5 train shards, verify 500-sample subset, export full SFT |

Phase 0: reuse [`deploy/distill/phase0/`](../distill/phase0/).

## Execution status (2026-05-25)

### Done

- Phase 1 scripts: `download.py`, `normalize.py`, `filter.py`, KodCode normalizer, pinned revision in `phase1/datasets.json`.
- Phase 2 scripts: `verify_subset.py`, `export_sft.py`.
- Pilot run: KodCode `train-00000-of-00005.parquet` slice, 1000 rows.

| Step | Result |
|------|--------|
| Download | 1000 raw rows → `phase1/cache/KodCode__KodCode-V1-SFT-4o/` |
| Normalize | 1000 rows (all `kodcode_leetcode`, Python) |
| Filter | 1000 kept; 0 benchmark leaks in this slice |
| Verify subset | **50/50 passed (100%)** with pytest via track venv |
| SFT export | `phase2/outputs/kodcode_pilot_sft.jsonl` (1000 rows) |

### Harness notes

- KodCode tests are **pytest**; the track venv must include `pytest` and be on `PATH` when calling the shared verifier (handled in `verify_subset.py`).
- Re-verification pass rate on this slice is high because upstream already verified solution+test pairs; treat this as a harness sanity check, not a quality filter.

### License (verified at pin)

- KodCode: **CC-BY-NC-4.0** at revision `14f8782fb7787c7e31dd4a1372518bc10fedb66e`. OK for private/local stack; re-check before any public release.

### Next

1. Scale download across all 5 train parquet shards (full KodCode subset).
2. Filter to Python-only or add TypeScript subsets when a TS dataset is added.
3. Proceed to Phase 3 student baseline (parent PLAN).

## Next actions

1. Pick the first dataset (default: `KodCode/KodCode-V1-SFT-4o`), pin a revision, and confirm the license string on that revision.
2. Write `phase1/download.py` and a KodCode-specific `normalize.py`. Emit ~1k rows for inspection.
3. Run `phase2/verify_subset.py` on the 1k sample as a harness sanity check.
4. If the sample looks clean, scale to the full filtered TS+Python subset and proceed to the student baseline.
