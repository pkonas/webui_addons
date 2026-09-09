# Architecture – e-INFRA Windows adapter 2.1.4

The target deployment is defined by `runtime.json` and consists of:

- Open WebUI bound to a loopback backend port;
- Caddy bound to public HTTP/HTTPS;
- two Scheduled Tasks using the shared `Run-Component.ps1` runner;
- a dedicated venv and data directory below the configured install root.

The adapter uses the internal loopback URL for authenticated Functions API operations and the public URL only for Caddy/TLS verification. It never sends the Open WebUI admin token through the public reverse proxy during installation.

## Backend ownership boundary

A process is eligible for termination only if it is:

- the verified `Run-Component.ps1 -Component Backend` runner;
- the configured `open-webui.exe`;
- an Open WebUI command running from the dedicated venv/base Python tree;
- or a descendant of one of these processes.

The adapter excludes Caddy and protects the current PowerShell process, the external manager Python and their ancestors.

## State transition contract

A restart is valid only after:

```text
Scheduled Task stopped
→ owned backend processes absent
→ backend port closed
→ task state not Running/Queued
→ Start-ScheduledTask
→ /api/version JSON
```

Task state `Ready` after a failed start means the task action is no longer running; it is not a successful readiness signal.

## Tutor runtime

The known-good Tutor runtime remains 1.26.2 and uses an ASGI prefix gateway. It does not mutate the private FastAPI route table. The actual health strategy is `asgi-prefix-gateway-v7`; router non-mutation is validated separately by `main_router_mutated=false`.
