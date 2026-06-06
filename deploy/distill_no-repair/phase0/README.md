# Phase 0 (shared)

Reuse the baseline harness in [`deploy/distill/phase0/`](../distill/phase0/):

```bash
cp deploy/distill/phase0/models.env.example deploy/distill/phase0/models.env
RUN_DIR="$(deploy/distill/phase0/preflight.sh | awk -F= '/^RUN_DIR=/{print $2}')"
deploy/distill/phase0/start_server.sh --run-dir "$RUN_DIR"
```

Or start the existing user service:

```bash
systemctl --user start llama-turbo-server.service
curl -fsS http://127.0.0.1:8080/health
```

Then continue with [`../README.md`](../README.md).
