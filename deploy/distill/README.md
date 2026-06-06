# Local Distillation Tutorial

This directory is a living, step-by-step tutorial for building a local coding-model distillation pipeline on top of `llama.cpp`.

The end goal is to turn a local teacher model into verified training data for an MTP-native student, then fine-tune adapters without destroying speculative decoding performance. The current state covers the first complete pilot loop:

1. Prove the model/runtime stack works.
2. Generate a small synthetic coding dataset.
3. Verify the generated samples.
4. Repair failed samples.
5. Re-verify until the pilot corpus is clean.

Keep raw outputs append-only. Treat verified and repaired datasets as derived artifacts.

## Current Status

The five-sample pilot has completed Phase 2 successfully after repair and stricter JavaScript test execution:

```text
input:  deploy/distill/phase2/outputs/pilot.repaired.v4.jsonl
output: deploy/distill/phase2/outputs/pilot.repaired.v4.verified.jsonl
total:  5
passed: 5
failed: 0
unverified: 0
```

The expanded 30-task pilot has also completed Phase 2 after verifier normalization and repair:

```text
input:  deploy/distill/phase2/outputs/expanded_pilot.repaired.v4.jsonl
output: deploy/distill/phase2/outputs/expanded_pilot.repaired.v4.verified.jsonl
total:  30
passed: 30
failed: 0
unverified: 0
```

The current scripts are intentionally small and inspectable. They are not yet a production training pipeline.

## Prerequisites

Start from the repository root:

```bash
cd /home/b/repos/llama-cpp-turboquant
```

You need:

- A working `llama.cpp` build with `llama-server`.
- A local OpenAI-compatible teacher endpoint.
- Python 3.
- Node.js and npm if you want TypeScript/JavaScript verification.
- `LLAMA_API_KEY` exported globally if the server requires auth.

Generated env files and outputs are ignored by git. Do not commit local API keys, downloaded models, generated run logs, or generated datasets unless you intentionally promote a small artifact for review.

## Phase 0: Prove The Runtime

Phase 0 establishes the baseline before generating data or training. It checks that the selected GGUF, `llama.cpp` build, GPU, port, and MTP settings are usable.

Copy the local config:

```bash
cp deploy/distill/phase0/models.env.example deploy/distill/phase0/models.env
```

Run preflight and start a baseline server:

```bash
RUN_DIR="$(deploy/distill/phase0/preflight.sh | awk -F= '/^RUN_DIR=/{print $2}')"
deploy/distill/phase0/start_server.sh --run-dir "$RUN_DIR"
```

Run a smoke set:

```bash
python3 deploy/distill/phase0/run_smoke.py \
  --run-dir "$RUN_DIR" \
  --prompts deploy/distill/phase0/prompts/smoke-10.jsonl
```

Stop the server and write a report:

```bash
deploy/distill/phase0/stop_server.sh --run-dir "$RUN_DIR"
python3 deploy/distill/phase0/report.py --run-root "$RUN_DIR"
```

Once the 10-prompt smoke set is stable, run the larger prompt set and a draft-length sweep:

```bash
deploy/distill/phase0/sweep_draft.sh \
  --drafts 1,2,3 \
  --prompts deploy/distill/phase0/prompts/smoke-50.jsonl
```

The important result is not just tokens/sec. Record the exact model, quant, command, context length, draft setting, hardware, and whether outputs look sane.

See `deploy/distill/phase0/README.md` for script details.

## Phase 1: Generate The Pilot Dataset

Phase 1 calls the local teacher through `/v1/chat/completions`, asks for a solution, then asks for tests. It writes structured JSONL and preserves raw response metadata.

Copy the config:

```bash
cp deploy/distill/phase1/generator.env.example deploy/distill/phase1/generator.env
```

Make sure the teacher server is healthy:

```bash
curl -fsS http://127.0.0.1:8080/health
```

Validate settings without calling the model:

```bash
python3 deploy/distill/phase1/generate_samples.py --dry-run
```

Generate the pilot:

```bash
python3 deploy/distill/phase1/generate_samples.py
```

Default output:

```text
deploy/distill/phase1/outputs/pilot.jsonl
```

After the five-sample pilot is clean, generate the expanded 30-task pilot into a separate file:

```bash
python3 deploy/distill/phase1/generate_samples.py \
  --prompts deploy/distill/phase1/prompts/expanded_pilot_tasks.jsonl \
  --output deploy/distill/phase1/outputs/expanded_pilot.jsonl \
  --max-samples 30
```

To keep the teacher busy for a longer unattended run, generate multiple raw candidates per prompt:

```bash
python3 deploy/distill/phase1/generate_samples.py \
  --prompts deploy/distill/phase1/prompts/expanded_pilot_tasks.jsonl \
  --output deploy/distill/phase1/outputs/expanded_pilot_candidates_10x.jsonl \
  --max-samples 30 \
  --candidates 10
```

This produces 300 raw samples with candidate IDs like `_c01` through `_c10`.

The generator currently disables hidden thinking for the answer turns:

```text
chat_template_kwargs.enable_thinking=false
```

This keeps the teacher from spending the whole token budget in `reasoning_content` and returning empty visible code. Reasoning traces should remain a separate experiment later; do not mix that decision into the basic dataset plumbing.

See `deploy/distill/phase1/README.md` for file layout and inspection commands.

## Phase 2: Verify And Repair

Phase 2 materializes each sample into a temporary work directory, runs language checks, writes verification metadata, and optionally asks the teacher to repair failed samples.

Copy the config:

```bash
cp deploy/distill/phase2/verifier.env.example deploy/distill/phase2/verifier.env
```

For full Node/TypeScript checks, set this in `deploy/distill/phase2/verifier.env`:

```bash
INSTALL_NODE_DEPS=true
```

This installs dependencies once in the shared `NODE_SANDBOX`, then symlinks `node_modules` into per-sample work directories. Use it only in an environment where you are comfortable executing generated code and tests.

Run verification:

```bash
python3 deploy/distill/phase2/verify_samples.py
```

Default outputs:

```text
deploy/distill/phase2/outputs/pilot.verified.jsonl
deploy/distill/phase2/outputs/pilot.verified.summary.json
```

Repair failures:

```bash
python3 deploy/distill/phase2/repair_failures.py
```

Re-verify repaired output:

```bash
python3 deploy/distill/phase2/verify_samples.py \
  --input deploy/distill/phase2/outputs/pilot.repaired.jsonl \
  --output deploy/distill/phase2/outputs/pilot.repaired.verified.jsonl
```

The pilot required several repair rounds. After strengthening JavaScript test execution, the final successful run was:

```bash
python3 deploy/distill/phase2/repair_failures.py \
  --input deploy/distill/phase2/outputs/pilot.repaired.v3.strict.verified.jsonl \
  --output deploy/distill/phase2/outputs/pilot.repaired.v4.jsonl

python3 deploy/distill/phase2/verify_samples.py \
  --input deploy/distill/phase2/outputs/pilot.repaired.v4.jsonl \
  --output deploy/distill/phase2/outputs/pilot.repaired.v4.verified.jsonl
```

Final result:

```text
total: 5
passed: 5
failed: 0
unverified: 0
```

See `deploy/distill/phase2/README.md` for verifier and repair-loop details.

For the expanded pilot, keep outputs separate from the five-sample pilot:

```bash
python3 deploy/distill/phase2/verify_samples.py \
  --input deploy/distill/phase1/outputs/expanded_pilot.jsonl \
  --output deploy/distill/phase2/outputs/expanded_pilot.verified.jsonl

python3 deploy/distill/phase2/repair_failures.py \
  --input deploy/distill/phase2/outputs/expanded_pilot.verified.jsonl \
  --output deploy/distill/phase2/outputs/expanded_pilot.repaired.jsonl

python3 deploy/distill/phase2/verify_samples.py \
  --input deploy/distill/phase2/outputs/expanded_pilot.repaired.jsonl \
  --output deploy/distill/phase2/outputs/expanded_pilot.repaired.verified.jsonl
```

The first expanded run went through four repair generations. The final clean verification command was:

```bash
python3 deploy/distill/phase2/verify_samples.py \
  --input deploy/distill/phase2/outputs/expanded_pilot.repaired.v4.jsonl \
  --output deploy/distill/phase2/outputs/expanded_pilot.repaired.v4.verified.jsonl
```

For large candidate runs, do not repair every failing candidate first. Verify the full raw file, select passing candidates by `meta.source_task_id`, and repair only groups that do not have enough passing candidates. When repairs are useful, run them in chunks:

```bash
python3 deploy/distill/phase2/select_solution_sft.py \
  --input deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.verified.jsonl \
  --output deploy/distill/phase2/outputs/solution_sft.seed_50x.max10.jsonl \
  --max-per-task 10 \
  --min-passing-per-task 10
```

This 50x run selected 247 balanced passing rows and wrote 413 failed IDs from weak groups:

```text
deploy/distill/phase2/outputs/solution_sft.seed_50x.max10.jsonl
deploy/distill/phase2/outputs/solution_sft.seed_50x.max10.weak_failed_ids.txt
```

```bash
python3 deploy/distill/phase2/repair_failures.py \
  --input deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.verified.jsonl \
  --output deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.repaired.batch001.jsonl \
  --ids-file deploy/distill/phase2/outputs/solution_sft.seed_50x.max10.weak_failed_ids.txt \
  --max-repairs 100
```

After repaired samples are re-verified, export successful repair attempts as a separate review/repair SFT dataset:

```bash
python3 deploy/distill/phase2/export_repair_sft.py \
  --input deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.repaired.verified.jsonl \
  --output deploy/distill/phase2/outputs/repair_sft.jsonl
```

For repair batches, write an ID file for touched rows before targeted re-verification:

```bash
python3 deploy/distill/phase2/write_repaired_ids.py \
  --input deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.weak_repaired.batch001.jsonl \
  --output deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.weak_repaired.batch001.ids.txt

python3 deploy/distill/phase2/verify_samples.py \
  --input deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.weak_repaired.batch001.jsonl \
  --output deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.weak_repaired.batch001.repaired_only.verified.jsonl \
  --ids-file deploy/distill/phase2/outputs/expanded_pilot_candidates_50x.weak_repaired.batch001.ids.txt
```

## Lessons From The Pilot

- Preflight matters. A running local service can occupy the target port before the baseline server starts.
- `LLAMA_API_KEY` should come from the environment or local env files and must not be printed into logs.
- Reasoning-enabled servers can return empty `content` if the request allows hidden thinking to consume the whole budget.
- Generated tests are often the weak link. They can overreach, assume the wrong runner, or assert brittle library internals.
- A sample should not be considered truly verified if only syntax checks ran while executable tests were present.
- The verifier should separate harness gaps from sample failures. Missing tools can be `unverified`; real failing checks should be `failed`.
- Shared dependency sandboxes are much faster than reinstalling Node packages per sample.
- Repair prompts work better when they force a clear classification: bad solution, bad tests, underspecified task, or harness issue.
- Repair attempts are valuable training data for a review agent, but only after the repaired sample verifies cleanly.

## Artifact Map

```text
deploy/distill/PLAN.md                         high-level roadmap
deploy/distill/README.md                       this living tutorial
deploy/distill/phase0/                         runtime baseline tools
deploy/distill/phase1/                         synthetic sample generation
deploy/distill/phase2/                         verification and repair
deploy/distill/phase1/prompts/expanded_pilot_tasks.jsonl  30-task expanded pilot prompt set
deploy/distill/phase1/outputs/pilot.jsonl      raw five-sample pilot samples
deploy/distill/phase1/outputs/expanded_pilot.jsonl        raw expanded pilot samples
deploy/distill/phase2/outputs/*.jsonl          derived verified/repaired samples
deploy/distill/phase2/outputs/work/            materialized sample workdirs
deploy/distill/phase2/outputs/node_sandbox/    shared Node dependency sandbox
```

## Next Steps

1. Run multi-candidate generation and measure first-pass verification rates.
2. Add best-of-N selection over candidate groups.
3. Add stronger static checks for tautological tests and unused assertions.
4. Add dataset cards with source, license, and generation settings.
5. Start Phase 3 only after the verified dataset process is repeatable.

