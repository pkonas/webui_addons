# Scheduled Task backend recovery contract

Use `-Action BackendRecovery` when the internal Open WebUI backend is unavailable. This action does not require an Open WebUI API token.

## Safe sequence

1. Parse the authoritative `runtime.json`.
2. Verify that the task action points at the configured runner and `-Component Backend`.
3. Stop only the backend task.
4. Kill only owned runner/backend processes, excluding Caddy and installer ancestors.
5. Require the backend port to close.
6. Require the task to leave `Running` and `Queued`.
7. Start the task once.
8. Require `/api/version` to return JSON.
9. If the task exits early, write full diagnostics.
10. If and only if the latest run shows a Tutor startup traceback and recovery mode is `Auto`, back up SQLite and deactivate only Tutor Function IDs before one clean retry.

## Why this is separate from Tutor installation

The Functions API cannot be used while Open WebUI is down. Backend recovery must therefore succeed before the transactional Tutor installer can authenticate, snapshot Functions, install the Pipe/Event pair and verify Canvas routes.
