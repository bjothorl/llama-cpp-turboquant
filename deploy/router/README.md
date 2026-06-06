# Agent router

`llama-agent-router.service` runs `llama-server` in **router mode**: one HTTP port, two models loaded on demand.

| Model ID | Weights | Role |
|----------|---------|------|
| `planner` | Qwen3.6-35B-A3B-MTP `UD-IQ4_XS` | Planning |
| `executor` | Qwen3.5-9B-MTP `UD-Q4_K_XL` | Parallel workers (`np=4`, 65k ctx/slot) |

Presets: [`models.ini`](models.ini). `--models-max 1` — only one model on GPU at a time (3090).

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
POST /models/load        {"model":"planner"}
POST /v1/chat/completions {"model":"planner", "messages":[...]}
POST /models/unload      {"model":"planner"}
POST /models/load        {"model":"executor"}
POST /v1/chat/completions {"model":"executor", "messages":[...]}  (×N parallel)
POST /models/unload      {"model":"executor"}
```

`GET /models` — status per model. `GET /props` — `"role":"router"`.

Executor requests: use `"chat_template_kwargs":{"enable_thinking":false}` so output lands in `content`.
