# Artifact and file bridge — v2.9.18

The self-contained installer embeds the entire PhysicsNeMo/NAT 1.2.10 component and Engineering MCP Tool Router 1.1.0. This file is descriptive; it is not an installation dependency.

Public MCP tools remain environment_info, solve, job_status, list_artifacts and get_artifact. The gateway adds render_artifacts plus signed artifact downloads. Solve accepts an optional client_request_id assigned by the authorized Open WebUI lifecycle wrapper. Job status accepts exactly one of job_id or client_request_id. Existing manual job_id calls remain supported. Internal source/workspace tools are not newly exposed as public MCP operations.

For wrapped chat calls, solve returns structured JSON including the actual answer, execution summary, delivery status and manifest. The wrapper publishes progress and an embed without requesting another model call. Unwrapped legacy callers keep the gateway's automatic inline-HTML behavior on completed/incomplete jobs. Gallery errors preserve the original result and add presentation diagnostics.

Data remains job-scoped. Existing path, filename, symlink and signed-download checks remain. Progress contains public phase descriptions and bounded numeric telemetry, not raw user text or raw model reasoning. Output verification is file-presence/size and subprocess exit-code verification, not scientific validation. Raw execution output stays in workspace/execution-*.log. User logs and configuration secrets are not included in this release.

See the Czech README for installation, runtime verification and limitations.
