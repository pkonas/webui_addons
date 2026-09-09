#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIRST_PARTY = [
    ROOT / "install-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1",
    ROOT / "recover-vut-ai-tutor-einfra-backend-v2.1.5.ps1",
    ROOT / "collect-vut-ai-tutor-einfra-diagnostics-v2.1.5.ps1",
    ROOT / "verify-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1",
    ROOT / "test-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1",
]

# Windows PowerShell 5.1 performs legacy native argument reconstruction. Embedded
# quotes in an inline python -c payload can therefore be removed before CPython
# sees them. First-party host scripts must execute real .py files instead.
patterns = {
    "direct_call_operator": re.compile(r"(?im)&\s*\$[A-Za-z_][A-Za-z0-9_]*\s+-c(?:\s|$)"),
    "argument_array": re.compile(r"(?i)@\(\s*['\"]-c['\"]"),
}
findings: list[dict[str, object]] = []
for path in FIRST_PARTY:
    text = path.read_text(encoding="utf-8-sig")
    for label, pattern in patterns.items():
        for match in pattern.finditer(text):
            findings.append({
                "file": path.name,
                "kind": label,
                "offset": match.start(),
                "snippet": match.group(0),
            })
if findings:
    raise SystemExit("unsafe inline python -c invocation remains: " + repr(findings))

test_script = FIRST_PARTY[-1].read_text(encoding="utf-8-sig")
if "python-host-probe-v2.1.5.py" not in test_script:
    raise SystemExit("Windows smoke test does not use the file-based Python host probe")
installer = FIRST_PARTY[0].read_text(encoding="utf-8-sig")
for required in ("create-selftest-db.py", "verify-selftest-db.py"):
    if required not in installer:
        raise SystemExit(f"adapter SelfTest lacks file-based helper {required}")

probe = ROOT / "tests" / "python-host-probe-v2.1.5.py"
completed = subprocess.run(
    [sys.executable, str(probe)],
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
if completed.returncode != 0:
    raise SystemExit("Python host probe failed: " + completed.stderr.strip())
try:
    result = json.loads(completed.stdout)
except json.JSONDecodeError as exc:
    raise SystemExit("Python host probe did not emit JSON") from exc
if not result.get("ok") or not result.get("version"):
    raise SystemExit("Python host probe returned an invalid success document")

print(json.dumps({
    "ok": True,
    "adapter": "2.1.5",
    "checked_powershell_files": len(FIRST_PARTY),
    "inline_python_c_findings": 0,
    "file_based_host_probe": True,
    "file_based_sqlite_selftest": True,
    "probe_version": result["version"],
}, ensure_ascii=True, sort_keys=True))
