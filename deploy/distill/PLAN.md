# Local Coding-Model Distillation Plan

## Goal

Build a fast local coding ecosystem with:

- `Qwen3.6-35B-A3B-MTP` as the local teacher and evaluator.
- An MTP-native Qwen3.5/Qwen3.6 student as the deployable runtime.
- Specialist LoRA adapters for TypeScript, Python, tests, debugging, refactors, and orchestration.
- `llama.cpp` `--spec-type draft-mtp` preserved end-to-end, measured by draft acceptance and tokens/sec instead of benchmark scores alone.

This is an execution plan for a private/local stack. Treat public release as a separate compliance and reproducibility project.

---

## Execution Status (as of 2026-05-25)

| Phase | Status | Notes |
|-------|--------|-------|
| **Phase 0** | Done (local) | `llama-server` + MTP smoke harness in [`deploy/distill/phase0/`](phase0/) |
| **Phase 1** | Done (pilots + 50×) | Two-turn generation; `expanded_pilot_candidates_50x.jsonl` = 1500 raw rows (30 tasks × 50 candidates) |
| **Phase 2 verify** | Done (50× mixed) | **614/1500 passed (40.9%)**, 886 failed, 0 unverified with `INSTALL_NODE_DEPS=true` |
| **Phase 2 repair** | Paused | 413 weak-group IDs; batches 001–002: **72/200** repair passes; 003–005 repaired but not re-verified. Use when repair SFT is needed. |
| **Phase 2 select** | Partial (50×) | `solution_sft.seed_50x.max10.jsonl` = **247** rows (21 tasks ≥10 passes); 9 weak tasks |
| **Prototype track** | **1500 done** | [`deploy/distill_no-repair/`](../distill_no-repair/): TS 30×50 — **784/1500 passed (52.3%)**, **256** SFT rows — see below |
| **Phase 3+** | Not started | Student MTP baseline, LoRA training, routing |

### Full-stack 50× verify (mixed languages, `deploy/distill/`)

| Task type | Pass rate |
|-----------|-----------|
| `typescript_bugfix` | **75%** (188/250) |
| `typescript_refactor` | **71%** (107/150) |
| `python_refactor` | **81%** (81/100) |
| `python_implementation` | **25%** (63/250) |
| `zod_schema` | **24%** (59/250) |
| `debugging` (JavaScript) | **28%** (70/250) |
| `react_component` | **18%** (46/250) |

Dominant failure checks: `node:vitest` (583), `typescript:tsc` (280). Generated tests are often the weak link, not solutions alone.

### Prototype track (`deploy/distill_no-repair/`)

TypeScript-only pipeline without repair: generate → verify → `select_passed`. Prompt curation in [`distill_no-repair/phase1/prompts/PROMPT_DESIGN.md`](../distill_no-repair/phase1/prompts/PROMPT_DESIGN.md).

**Calibration run** (10 tasks × 5 candidates = 50, `typescript_tasks_calibrate.jsonl`):

| Metric | First verify | After harness fixes |
|--------|--------------|---------------------|
| Overall | 16/50 (**32%**) | **23/50 (46%)** |
| `typescript_bugfix` | 9/10 | 9/10 (90%) |
| `typescript_refactor` | 6/10 | 6/10 (60%) |
| `react_component` | 0/15 | **7/15 (47%)** |
| `zod_schema` | 1/15 | 1/15 (7%) |

Artifacts: `distill_no-repair/phase1/outputs/calibrate_10x5.jsonl`, `phase2/outputs/calibrate_10x5.verified.jsonl`, `calibrate_10x5.analysis.txt`.

**Full TS run** (30 tasks × 50, `typescript_tasks_30.jsonl`, no repair):

| Metric | Value |
|--------|-------|
| Verified | `typescript_candidates_50x.verified.jsonl` |
| **Pass rate** | **784/1500 (52.3%)** |
| SFT export | `solution_sft.jsonl` — **256** rows (`--max-per-task 10`) |

| Task type | Pass rate |
|-----------|-----------|
| `typescript_bugfix` | 81.8% |
| `typescript_refactor` | 63.0% |
| `react_component` | 40.5% |
| `zod_schema` | 26.5% |

| Tier | Pass rate |
|------|-----------|
| `proven` | 59.5% |
| `revised` | 54.7% |
| `baseline` | 6.7% (keep for regression only) |

Details and next steps: [`distill_no-repair/PLAN.md`](../distill_no-repair/PLAN.md).

**Verifier harness fixes applied** (in both `distill/` and `distill_no-repair/` `verify_samples.py`):

1. **jest-dom for Vitest** — `vitest.setup.ts` + `setupFiles` when tests use RTL matchers (`toHaveClass`, `toBeInTheDocument`, etc.). React went from 0% → ~47% on calibration.
2. **Markdown fence stripping** — `strip_markdown_fences()` in `normalize_js_ts_tests()` removes ` ```typescript ` wrappers from test turns. Helps parse errors; does not fix truncated test files.

**Still open (verifier / generation hints):**

- Zod tests using `.error.errors` instead of Zod 4 `.issues`
- `tsc` failing on unused `@ts-expect-error` in tests while Vitest passes
- Truncated test generation (`MAX_TOKENS_TESTS`) and bad assertions (e.g. wrong sort order in bugfix tests)
- Async React tests that contradict the prompt (e.g. “disabled initially”)

**Lessons learned**

- ~40–52% first-pass verify yield is viable for prototype SFT without repair (TS-only 30×50 reached **52.3%**).
- React failures were largely harness + test quality, not broken components.
- Zod failures mix truncated tests, API mismatch, and assertion issues — not fixed by jest-dom alone.
- Repair loop remains valuable but too slow for iteration; use `distill_no-repair` until prompts and harness stabilize.

---

## Non-Negotiable Constraints

### MTP is architecture, not data

`draft-mtp` depends on model weights and metadata, not on the training corpus. In llama.cpp, MTP-capable Qwen models include extra NextN/MTP tensors and `nextn_predict_layers > 0`. The main trunk predicts the next token; the MTP path drafts future tokens that the main path verifies.

MTP survives only if:

1. The student checkpoint already ships with MTP weights.
2. The GGUF conversion preserves the MTP tensors and `nextn_predict_layers` metadata.
3. SFT/LoRA does not shift the main-token distribution so far that MTP draft acceptance collapses.

Do not use Qwen2.5-Coder, DeepSeek-Coder, or any other non-MTP checkpoint as the deployable student for this stack. They may be useful baselines, but they cannot run `draft-mtp` internally.

### Use only permitted training data

Do not train a release-bound open-ended coding model on Claude/Opus outputs unless there is explicit permission for that use. The previously listed Opus datasets are real, but their contents are not automatically safe for distilling a competing general-purpose/code-generation model.

Allowed by default:

- Locally generated samples from models whose license/terms allow this use.
- User-owned repositories and tasks.
- Open datasets whose license and terms permit SFT/distillation for code generation.
- Verified coding datasets such as `KodCode/KodCode-V1-SFT-4o`, after checking the dataset license and downstream-use requirements.

Quarantine unless approved:

- `yikes-liki/claude-opus-4.6-4.7-reasoning-8.7k`
- `lordx64/reasoning-distill-opus-4-7-max-sft`
- Any dataset advertised as Claude, Opus, ChatGPT, Gemini, or other hosted frontier-model output without clear redistribution/training rights.

### Reasoning traces are optional

Keep reasoning data as a separate field. Train one adapter with reasoning enabled and one without before committing to a global policy. Reasoning-heavy SFT can improve problem solving, but it can also increase verbosity, leak unwanted `<think>` style into user-visible outputs, and make evaluation noisier.

---

# Phase 0 - Prove The Stack Before Generating Data

## Objective

Confirm that the exact model, quant, llama.cpp build, and hardware can run MTP and report a stable baseline.

## Candidate models

| Model | Role | Notes |
|-------|------|-------|
| `unsloth/Qwen3.5-9B-MTP-GGUF` | Primary student | Smallest practical MTP-native target. Verify llama.cpp support with the current build. |
| `unsloth/Qwen3.6-27B-MTP-GGUF` | Larger student fallback | Better capability, higher VRAM. |
| `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` | Teacher | Already used by the local service file. |

## Baseline command

Start with the same pattern as `deploy/llama-turbo-server.service`:

```bash
./build/bin/llama-server \
  -hf unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-IQ4_XS \
  --reasoning on \
  --reasoning-format deepseek \
  --spec-type draft-mtp \
  --spec-draft-n-max 2 \
  --host 127.0.0.1 \
  --port 8080 \
  -ngl 99 \
  -fa on \
  -c 8192 \
  -np 1
```

Use a shorter context first. Increase context only after MTP speed and VRAM headroom are known.

## Required checks

- GGUF metadata shows `nextn_predict_layers > 0`.
- `llama-server` starts with `--spec-type draft-mtp --spec-draft-n-max 2`.
- No degenerate loops or obvious formatting failures across a 50-prompt coding smoke set.
- Record baseline tokens/sec, draft acceptance, VRAM, context length, quant, commit SHA, and exact command.
- Repeat with `--spec-draft-n-max` values `1`, `2`, `3`, and optionally `4`; keep the fastest stable value, not necessarily the largest value.

Do not start training until the student baseline is measured. The student is compared against its own pre-SFT baseline, not against the 35B teacher.

---

# Phase 1 - Build Synthetic Dataset Pipeline

## Objective

Turn the teacher into a continuous coding-data generator with raw-response capture, repeatable prompts, and verification metadata.

## Prompt generator

Generate tasks for:

- TypeScript bug fixes, React components, Next.js APIs, tRPC routers, Zod schemas, and refactors.
- Python utilities, CLI tools, data transforms, and pytest tasks.
- Test-writing from implementation and implementation from tests.
- Debugging tasks with failing logs.
- Small architecture/design tasks that produce code and tests.

Use prompt sources in this order:

1. Handwritten templates.
2. User-owned codebases.
3. Permissively licensed public code snippets with attribution metadata.
4. Generated prompts from the local teacher.

## Teacher generation

Use two turns per sample:

1. Solve the task and produce code.
2. Write or repair tests for the produced code.

Capture:

- Raw API response.
- Parsed answer text.
- Parsed reasoning, if present.
- Extracted code blocks.
- Test blocks.
- Model, quant, sampling params, prompt template version, and generation timestamp.

Prefer OpenAI-compatible `/v1/chat/completions` so the same pipeline can target llama.cpp and other local runtimes.

## JSONL schema

```json
{
  "id": "typescript_refactor_000001_c03",
  "task_type": "typescript_refactor",
  "language": "typescript",
  "source": {
    "kind": "synthetic_template",
    "license": "local",
    "uri": null
  },
  "prompt": "...",
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "reasoning": "...",
  "code": "...",
  "tests": "...",
  "verification": {
    "compile": null,
    "lint": null,
    "tests": null,
    "score": null
  },
  "meta": {
    "teacher": "unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-IQ4_XS",
    "candidate": 3,
    "sampling": {
      "temperature": 0.6,
      "top_p": 0.95,
      "top_k": 20,
      "min_p": 0.0
    },
    "raw": {}
  }
}
```

Save raw samples append-only. Write filtered/verified datasets as derived artifacts; never mutate the raw corpus.

---

# Phase 2 - Build Dataset Quality Layer

## Objective

Promote only samples that compile, run, and teach the desired behavior.

## Verification

For TypeScript:

- Install dependencies in a sandbox.
- Run `tsc --noEmit`.
- Run ESLint if the task includes a project config.
- Run unit tests.

For Python:

- Run syntax checks.
- Run `pytest`.
- Prefer isolated execution for generated code.

For all samples:

- Reject code that imports undeclared dependencies unless dependency selection is part of the task.
- Reject tests that only assert mocks, snapshots, or tautologies.
- Penalize solutions that ignore the prompt, omit requested tests, or hide work in comments.
- Keep failure logs for later debugging and prompt repair.

## Best-of-N

Generate 4-8 candidates per prompt. Select by:

1. Test/compile pass.
2. Minimal patch size for edit tasks.
3. Simplicity and maintainability.
4. Teacher or local evaluator score as a tie-breaker only.

Avoid over-filtering early. Keep enough near-misses to improve prompt templates and build negative examples later.

---

# Phase 3 - Select The Student

## Objective

Pick one MTP-native base model and freeze it as the universal coding brain. Specialists are adapters on top of this base, not separate model families.

## Selection gates

The chosen student must:

- Load in the current llama.cpp build.
- Run with `--spec-type draft-mtp`.
- Show `nextn_predict_layers > 0`.
- Fit target hardware at the intended quant and context.
- Have an acceptable pre-SFT coding baseline.
- Have a clear path from HF weights to training format and back to GGUF.

## Baseline matrix

Record at least:

| Variant | Quant | Context | `spec-draft-n-max` | Acceptance | Tok/s | VRAM | Notes |
|---------|-------|---------|--------------------|------------|-------|------|-------|
| 9B MTP | TBD | 8192 | 1 | TBD | TBD | TBD | student candidate |
| 9B MTP | TBD | 8192 | 2 | TBD | TBD | TBD | student candidate |
| 27B MTP | TBD | 8192 | 2 | TBD | TBD | TBD | fallback |

Pick the smallest model that passes quality and speed gates. Larger is a fallback, not the default.

---

# Phase 4 - Train Specialized LoRAs

## Objective

Create modular specialists without damaging MTP throughput.

Initial adapters:

- `typescript`
- `python`
- `tests`
- `debugging`
- `refactor`

## Training policy

- Train adapters only; keep base weights frozen.
- Start with attention-only LoRA targets.
- Do not merge adapters into the base unless a deployment constraint requires it.
- Use assistant-only loss for conversational data.
- Keep reasoning-on and reasoning-off datasets separate.
- Track exact adapter target modules, rank, alpha, dropout, sequence length, learning rate, optimizer, and dataset version.

Do not assume an adapter is MTP-safe. Every adapter gets its own MTP acceptance and tokens/sec measurement.

## Adapter acceptance gate

An adapter can be used only if:

- Coding eval improves or is neutral for its target domain.
- Non-target regressions are understood.
- Draft acceptance remains at least 80% of the untuned student baseline for the same quant/context/spec settings.
- Tokens/sec does not regress enough to remove the benefit of `draft-mtp`.
- Output format remains compatible with the routing system.

If attention-only LoRA still collapses acceptance, narrow the target modules, lower rank, reduce scale, or split the domain.

---

# Phase 4.5 - MTP Realignment Research

## Objective

Recover draft acceptance after a useful adapter or SFT recipe shifts the main-head distribution.

This is not a required first milestone. It is a research branch unless LoRA training measurably damages MTP.

## Procedure

1. Establish pre-adapter MTP logits/acceptance baselines on a held-out code corpus.
2. Apply the trained adapter and measure the new main-head distribution and MTP acceptance.
3. If acceptance drops below the gate, experiment with MTP-head-only or MTP-module-targeted training.
4. Freeze the main trunk during realignment.
5. Use self-distillation from the adapted main path: MTP predicts the adapted main path's next-token distribution.
6. Export, convert, quantize, and re-measure on the same hardware.

Open implementation questions that must be resolved before this phase is executable:

- Which HF module names correspond to Qwen3.5/Qwen3.6 MTP heads for the chosen checkpoint?
- Which trainer supports those modules without breaking the base model or LoRA export?
- How are MTP-head updates represented when converting back to GGUF?
- Does llama.cpp apply runtime LoRA to the MTP graph path, the main graph path, or both for the selected architecture?

Do not ship a model that requires Phase 4.5 until these questions are answered with tests.

---

# Phase 5 - Runtime Routing

## Objective

Dynamically activate adapters while keeping one MTP-native base loaded.

Preferred deployment:

```bash
./build/bin/llama-server \
  -hf <student-mtp-gguf> \
  --spec-type draft-mtp \
  --spec-draft-n-max 2 \
  --lora-scaled adapters/typescript.gguf:0.0,adapters/tests.gguf:0.0 \
  --lora-init-without-apply \
  -np 1
```

Route per request with the `lora` field or `/lora-adapters`, for example:

```json
[
  {"id": 0, "scale": 1.0},
  {"id": 1, "scale": 0.0}
]
```

Routing rules:

- Runtime routing is preferred.
- Adapter stacking is allowed only after measuring each combination.
- Adapter merging is a last resort and requires a full MTP re-baseline.
- Requests with different LoRA configs may batch less efficiently; include that in throughput tests.

---

# Evaluation

## Required evals

- Domain coding tasks for each adapter.
- Held-out generated tasks from the same distribution.
- Human-authored smoke tasks from the target workflow.
- Negative tests for hallucinated APIs and missing dependencies.
- MTP acceptance/tok/s for base, each adapter, and common adapter stacks.

## Required artifacts

Each run should produce:

- Dataset version.
- Training config.
- Adapter artifact path.
- llama.cpp commit SHA.
- Model ID, quant, context, and command line.
- Coding metrics.
- MTP metrics.
- Failure examples.

---

# Long-Term Optional Phase - True Compression

Only explore this after dataset generation, LoRA training, routing, and MTP measurement are stable.

Possible work:

- Layer dropping.
- Architectural compression.
- New smaller student architecture.
- MTP-preserving distillation or MTP head transplantation.

This is research-level work. Do not make it part of the first usable system.

---

# Core Principles

1. Data quality beats model-size churn.
2. MTP is a runtime contract: preserve weights, metadata, alignment, and throughput.
3. Capability SFT and MTP realignment are separate problems.
4. Keep legal provenance attached to every sample.
5. Validate on the target quant and hardware before declaring success.

---

# Immediate Next Actions

1. **Prototype:** Scale [`deploy/distill_no-repair/`](../distill_no-repair/) — `./run_pipeline.sh` (30×50) or 18×50 baseline; export `solution_sft.jsonl`.
2. **Prototype:** Improve tests-turn hints (Zod 4 `.issues`, fewer Tailwind/class assertions, no contradictory async tests); optional bump `MAX_TOKENS_TESTS`.
3. **Harness:** Add remaining verifier tweaks (unused `@ts-expect-error` in tests, Zod API normalization) and re-calibrate.
4. **Phase 3:** Measure student baselines for `Qwen3.5-9B-MTP` / `Qwen3.6-27B-MTP` with `--spec-type draft-mtp`.
5. Train one small TypeScript LoRA; compare base vs adapter for quality, draft acceptance, and tokens/sec.
6. **(Optional)** Resume repair batches 003–005 in `deploy/distill/` when repair SFT is needed.
