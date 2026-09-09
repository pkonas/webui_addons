#!/usr/bin/env python3
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
path = root / "install-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1"
text = path.read_text(encoding="utf-8-sig")
required = [
    "Stop-EInfraBackendCompletely",
    "Stop-EInfraBackendProcesses",
    "Wait-BackendPortReleased",
    "Wait-EInfraBackendTaskQuiescent",
    "Get-ScheduledTaskInfo",
    "LastTaskResultHex",
    "Save-BackendFailureDiagnostics",
    "Invoke-OfflineTutorFunctionDeactivation",
    "Test-RestartUsefulAfterEngineFailure",
    "BackendRecovery",
    "ConvertTo-TaskDateTimeText",
    "New-TaskDiagnosticRecord",
    "Synthetic null TaskInfo",
    "Test-BackendRunStartLine",
    "BackendRunStartPattern",
]
missing = [item for item in required if item not in text]
if missing:
    raise SystemExit("missing recovery symbols: " + repr(missing))

match = re.search(r"function Stop-EInfraBackendCompletely\s*\{(?P<body>.*?)\n\}", text, re.S)
if not match:
    raise SystemExit("Stop-EInfraBackendCompletely was not found")
body = match.group("body")
sequence = [
    "Stop-ScheduledTask",
    "Stop-EInfraBackendProcesses",
    "Wait-BackendPortReleased",
    "Wait-EInfraBackendTaskQuiescent",
]
positions = [body.find(item) for item in sequence]
if any(value < 0 for value in positions) or positions != sorted(positions):
    raise SystemExit("invalid backend stop ordering: " + repr(dict(zip(sequence, positions))))

start_match = re.search(r"function Start-EInfraBackendTask\s*\{(?P<body>.*?)\n\}", text, re.S)
if not start_match:
    raise SystemExit("Start-EInfraBackendTask was not found")
start_body = start_match.group("body")
if start_body.find("Wait-EInfraBackendTaskQuiescent") > start_body.find("Start-ScheduledTask"):
    raise SystemExit("task quiescence is checked after Start-ScheduledTask")
if "LastTaskResultHex" not in text or "BackendLogAdvancedAfterStart" not in text:
    raise SystemExit("startup diagnostics are incomplete")
if "if ($result.ExitCode -ne 0 -and $Action -in @('Install','Repair') -and $RestartPolicy -eq 'OnFailure')" in text:
    raise SystemExit("unbounded legacy restart condition remains")

print({
    "ok": True,
    "adapter": "2.1.5",
    "required_symbols": len(required),
    "stop_sequence": sequence,
    "task_quiescence_before_start": True,
    "fail_fast_diagnostics": True,
})

source = path.read_text(encoding="utf-8-sig")
for unsafe in (".LastRunTime.ToString(", ".NextRunTime.ToString("):
    if unsafe in source:
        raise SystemExit("null-unsafe Task Scheduler time formatting remains: " + unsafe)
