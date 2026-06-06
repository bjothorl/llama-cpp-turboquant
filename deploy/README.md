# Deploy

Systemd unit files live in this repo. **systemd does not read them from here.**

## Single model (35B)

Unit: [`llama-turbo-server.service`](llama-turbo-server.service)

```bash
./deploy/install.sh
systemctl --user status llama-turbo-server.service
```

## Agent router (35B planner + 9B executor)

Unit: [`deploy/router/llama-agent-router.service`](router/llama-agent-router.service)

```bash
./deploy/router/install.sh
systemctl --user enable --now llama-agent-router.service
journalctl --user -u llama-agent-router.service -f
```

See [`deploy/router/README.md`](router/README.md). Do not run both services on port 8080.

Optional environment variables (for example `HF_TOKEN`) can go in `~/.config/llama-server/env`; see the commented `EnvironmentFile` line in each unit file.
