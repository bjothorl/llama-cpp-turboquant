# Agent router

`llama-agent-router.service` runs `llama-server` in **router mode**: one HTTP port, two models loaded on demand.

| Model ID | Weights | Role |
|----------|---------|------|
| `planner` | Qwen3.6-35B-A3B-MTP `UD-IQ4_XS` | Planning |
| `executor` | Qwen3.5-9B-MTP `UD-Q4_K_XL` | Parallel workers (`np=4`, 65k ctx/slot) |
| `vibethinker3b` | VibeThinker-3B `i1-IQ4_XS` | Lightweight reasoning (Qwen2, no MTP) |
| `gemma431b` | Gemma 4 31B `UD-Q4_K_XL` + MTP | Dense planner (thinking off, tools/agents) |
| `gemma431b-thinking` | Gemma 4 31B `UD-Q4_K_XL` + MTP | Same model with thinking enabled |

Presets: [`models.ini`](models.ini). `--models-max 1` — only one model on GPU at a time (3090). Models autoload on first request (`"model": "planner"`, `"executor"`, `"vibethinker3b"`, `"gemma431b"`, or `"gemma431b-thinking"`).

## Install

Stop the single-model service if it uses port 8080:

```bash
systemctl --user stop llama-turbo-server.service
```

From repo root:

```bash
./deploy/router/install.sh
systemctl --user enable --now llama-agent-router.service
```

Logs:

```bash
journalctl --user -u llama-agent-router.service -f
```

## Remote API

```http
POST /v1/chat/completions {"model":"planner", "messages":[...]}
POST /v1/chat/completions {"model":"executor", "messages":[...]}  (×N parallel)
POST /v1/chat/completions {"model":"vibethinker3b", "messages":[...]}
POST /v1/chat/completions {"model":"gemma431b", "messages":[...]}
POST /v1/chat/completions {"model":"gemma431b-thinking", "messages":[...]}
```

Models autoload if not loaded. Loading one evicts the other (`--models-max 1`).

Optional: `POST /models/unload {"model":"planner"}` to free GPU without chatting.

`GET /models` — status per model. `GET /props` — `"role":"router"`.

Executor requests: use `"chat_template_kwargs":{"enable_thinking":false}` so output lands in `content`.
