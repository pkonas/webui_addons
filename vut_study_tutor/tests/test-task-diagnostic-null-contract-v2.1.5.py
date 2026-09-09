#!/usr/bin/env python3
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
installer = (root / "install-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1").read_text(encoding="utf-8-sig")
collector = (root / "collect-vut-ai-tutor-einfra-diagnostics-v2.1.5.ps1").read_text(encoding="utf-8-sig")

for name, text in (("installer", installer), ("collector", collector)):
    for unsafe in (".LastRunTime.ToString(", ".NextRunTime.ToString("):
        if unsafe in text:
            raise SystemExit(f"{name} contains null-unsafe conversion: {unsafe}")
    if "ConvertTo-TaskDateTimeText" not in text:
        raise SystemExit(f"{name} lacks ConvertTo-TaskDateTimeText")

required_installer = (
    "New-TaskDiagnosticRecord",
    "LastRunTime = ConvertTo-TaskDateTimeText -Value $lastRunRaw",
    "NextRunTime = ConvertTo-TaskDateTimeText -Value $nextRunRaw",
    "LastRunTime=$null; NextRunTime=$null",
    "Synthetic missing TaskInfo properties",
    "$taskStateCanProveExit",
)
missing = [value for value in required_installer if value not in installer]
if missing:
    raise SystemExit("installer null-regression contract incomplete: " + repr(missing))

# The production query function must delegate formatting to a pure record builder,
# which is exercised by -Action SelfTest without touching the real Task Scheduler.
match = re.search(r"function Get-TaskDiagnostic\s*\{(?P<body>.*?)\n\}", installer, re.S)
if not match or "New-TaskDiagnosticRecord" not in match.group("body"):
    raise SystemExit("Get-TaskDiagnostic does not delegate to the null-safe record builder")

print({
    "ok": True,
    "adapter": "2.1.5",
    "null_last_run_time": "covered",
    "null_next_run_time": "covered",
    "missing_properties": "covered",
    "collector": "covered",
})
