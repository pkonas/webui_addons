# Test results – e-INFRA adapter 2.1.5

## Passed in the build container

- Python compilation of engine, runtime, host probe and all regression tests.
- Embedded Universal Engine byte/hash contract.
- Backend log start-header regex against bare, absolute and quoted paths.
- Isolation of a previous Tutor error from the newest unrelated backend run.
- Positive detection of a Tutor failure in the newest backend run.
- Retention of the newest run header while truncating a long log excerpt.
- Adapter recovery ordering, Task Scheduler null values and restart guard.
- Runtime health/Canvas/CORS contract.
- File-based Python host probe and SQLite helper contracts.
- No first-party PowerShell `python -c` invocation.
- UTF-8 BOM and CRLF checks for production PowerShell files.
- PowerShell lexical delimiter/string balance.
- ZIP and TAR.GZ extraction plus SHA-256 verification.

## Not executed in the Linux build container

- Native Windows PowerShell 5.1 execution.
- Real `Get-ScheduledTaskInfo` against the Pelton Task Scheduler.
- Live restart of `e-INFRA Open WebUI Backend`.

The included Windows smoke test executes the corrected adapter self-test before
any access to production `runtime.json` or Scheduled Tasks.
