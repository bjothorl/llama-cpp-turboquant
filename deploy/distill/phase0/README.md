# Phase 0 Baseline Tools

This directory contains a small harness for proving that an MTP-capable GGUF works with the local `llama.cpp` build before generating data or training LoRAs.

## Quick Start

```bash
cd /home/b/repos/llama-cpp-turboquant
cp deploy/distill/phase0/models.env.example deploy/distill/phase0/models.env
# If your server requires auth, add this to models.env:
# LLAMA_API_KEY=...

RUN_DIR="$(deploy/distill/phase0/preflight.sh | awk -F= '/^RUN_DIR=/{print $2}')"
deploy/distill/phase0/start_server.sh --run-dir "$RUN_DIR"
python3 deploy/distill/phase0/run_smoke.py --run-dir "$RUN_DIR" --prompts deploy/distill/phase0/prompts/smoke-10.jsonl
deploy/distill/phase0/stop_server.sh --run-dir "$RUN_DIR"
python3 deploy/distill/phase0/report.py --run-root "$RUN_DIR"
```

For a draft-length sweep:

```bash
deploy/distill/phase0/sweep_draft.sh --drafts 1,2,3 --prompts deploy/distill/phase0/prompts/smoke-10.jsonl
```

Use `smoke-50.jsonl` once the 10-prompt run is stable.

## Files

- `models.env.example` - default model and server settings.
- `preflight.sh` - checks binary, git state, GPU visibility, and port availability.
- `start_server.sh` - starts one `llama-server` instance and writes logs/artifacts.
- `stop_server.sh` - stops the server started for a run directory.
- `run_smoke.py` - sends OpenAI-compatible chat requests and summarizes responses.
- `sweep_draft.sh` - repeats the smoke run for multiple `--spec-draft-n-max` values.
- `report.py` - combines run artifacts into `baseline.json` and `baseline.md`.
- `prompts/` - small JSONL prompt sets for coding smoke tests.
- `runs/` - generated run artifacts.

## Notes

The scripts use Bash, Python standard library, `curl`, and optional `nvidia-smi`. They intentionally mark acceptance as `not_reported` if the current build does not print an obvious speculative acceptance metric in logs.

If `LLAMA_API_KEY` is set in the environment or in `models.env`, `start_server.sh` exports it for `llama-server`, authenticated readiness checks use it, and `run_smoke.py` sends it as `Authorization: Bearer ...`. `run_smoke.py` reads `deploy/distill/phase0/models.env` by default, so the direct command in the quick start works without manually exporting the key. The key is not written to command logs or reports.
