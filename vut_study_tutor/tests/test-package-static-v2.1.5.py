#!/usr/bin/env python3
from __future__ import annotations

import gzip
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PS_FILES = sorted(path for path in ROOT.rglob("*.ps1") if "reference" not in path.parts)

if not PS_FILES:
    raise SystemExit("no PowerShell files found")

unsafe_colon = re.compile(r"(?<![A-Za-z0-9_])\$([A-Za-z_][A-Za-z0-9_]*)\s*:")
common = {
    "verbose", "debug", "erroraction", "warningaction", "informationaction",
    "progressaction", "errorvariable", "warningvariable", "informationvariable",
    "outvariable", "outbuffer", "pipelinevariable", "whatif", "confirm",
}

for path in PS_FILES:
    data = path.read_bytes()
    if not data.startswith(b"\xef\xbb\xbf"):
        raise SystemExit(f"missing UTF-8 BOM: {path.relative_to(ROOT)}")
    if b"\n" in data.replace(b"\r\n", b""):
        raise SystemExit(f"bare LF found: {path.relative_to(ROOT)}")
    text = data.decode("utf-8-sig")
    if re.search(r"(?im)&\s*\$[A-Za-z_][A-Za-z0-9_]*\s+-c(?:\s|$)", text):
        raise SystemExit(f"unsafe direct python -c invocation in {path.name}")
    if re.search(r"(?i)@\(\s*['\"]-c['\"]", text):
        raise SystemExit(f"unsafe argument-array python -c invocation in {path.name}")
    if "[CmdletBinding" in text:
        # An advanced script receives common parameters automatically and must not
        # redeclare them in its top-level param block.
        prefix = text[: text.find("Set-StrictMode") if "Set-StrictMode" in text else 5000]
        declarations = {m.group(1).lower() for m in re.finditer(r"\$([A-Za-z_][A-Za-z0-9_]*)", prefix)}
        collision = sorted(common & declarations)
        if collision:
            raise SystemExit(f"common parameter collision in {path.name}: {collision}")
    for match in unsafe_colon.finditer(text):
        name = match.group(1)
        if name.lower() not in {"env", "global", "script", "local", "private", "using", "variable", "function", "alias"}:
            raise SystemExit(f"unsafe variable-colon interpolation ${name}: in {path.name}")

installer = ROOT / "install-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1"
source = installer.read_text(encoding="utf-8-sig")
for forbidden in (".LastRunTime.ToString(", ".NextRunTime.ToString("):
    if forbidden in source:
        raise SystemExit(f"null-unsafe Task Scheduler timestamp conversion remains: {forbidden}")
for required_symbol in ("ConvertTo-TaskDateTimeText", "New-TaskDiagnosticRecord", "Synthetic null TaskInfo", "Test-BackendRunStartLine", "BackendRunStartPattern"):
    if required_symbol not in source:
        raise SystemExit(f"missing Task Scheduler null-safety contract: {required_symbol}")
collector = (ROOT / "collect-vut-ai-tutor-einfra-diagnostics-v2.1.5.ps1").read_text(encoding="utf-8-sig")
for forbidden in (".LastRunTime.ToString(", ".NextRunTime.ToString("):
    if forbidden in collector:
        raise SystemExit(f"collector retains null-unsafe timestamp conversion: {forbidden}")
payload_match = re.search(r"\$EmbeddedEnginePayload\s*=\s*'([^']+)'", source)
hash_match = re.search(r"\$ExpectedEngineSha256\s*=\s*'([0-9a-f]{64})'", source)
if not payload_match or not hash_match:
    raise SystemExit("embedded engine payload contract missing")
embedded = gzip.decompress(__import__("base64").b64decode(payload_match.group(1)))
external_path = ROOT / "engine" / "install-vut-ai-tutor-universal-v2.0.2.ps1"
external = external_path.read_bytes()
if embedded != external:
    raise SystemExit("embedded engine bytes differ from external engine")
actual = hashlib.sha256(embedded).hexdigest()
if actual != hash_match.group(1):
    raise SystemExit(f"embedded engine hash mismatch: {actual}")

required_files = {
    "install-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1",
    "recover-vut-ai-tutor-einfra-backend-v2.1.5.ps1",
    "collect-vut-ai-tutor-einfra-diagnostics-v2.1.5.ps1",
    "verify-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1",
    "test-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1",
    "tests/python-host-probe-v2.1.5.py",
    "tests/test-powershell-python-invocation-contract-v2.1.5.py",
    "tests/test-adapter-python-helpers-v2.1.5.py",
    "tests/test-powershell-here-string-contract-v2.1.5.py",
    "tests/test-powershell-lexical-balance-v2.1.5.py",
    "tests/test-log-segmentation-contract-v2.1.5.py",
    "README.md",
}
missing = sorted(name for name in required_files if not (ROOT / name).is_file())
if missing:
    raise SystemExit("package missing files: " + repr(missing))

print({
    "ok": True,
    "powershell_files": len(PS_FILES),
    "embedded_engine_exact": True,
    "embedded_engine_sha256": actual,
    "common_parameter_collisions": 0,
    "unsafe_variable_colon_findings": 0,
    "utf8_bom_crlf": True,
    "inline_python_c_findings": 0,
})
