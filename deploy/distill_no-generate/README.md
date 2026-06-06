# distill_no-generate

Downloaded-data SFT track. No local teacher generation. See [`PLAN.md`](PLAN.md).

## Setup

```bash
cd deploy/distill_no-generate
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Pilot (KodCode, 1000 rows)

```bash
./run_pilot.sh
```

## Full KodCode (all 5 train shards, ~409k rows)

```bash
./run_full.sh
```

Environment overrides: `MAX_ROWS` (per shard, 0 = all), `TRAIN_SHARDS`, `SAMPLE_SIZE`, `DATASET_ID`, `SFT_OUTPUT`.

Pilot overrides: `MAX_ROWS`, `SAMPLE_SIZE`, `DATASET_ID`.

Artifacts:

- `phase1/cache/KodCode__KodCode-V1-SFT-4o/` — raw download + manifest
- `phase1/outputs/KodCode__KodCode-V1-SFT-4o.filtered.jsonl` — normalized + filtered
- `phase2/outputs/KodCode__KodCode-V1-SFT-4o.pilot.verified.jsonl` — harness check on a stratified subset

Sibling tracks:

- [`../distill/`](../distill/) — full pipeline with repair loop.
- [`../distill_no-repair/`](../distill_no-repair/) — local generation, verify-only.
