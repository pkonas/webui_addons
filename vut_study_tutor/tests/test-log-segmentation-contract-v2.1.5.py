#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1"
SOURCE = INSTALLER.read_text(encoding="utf-8-sig")

match = re.search(r"\$script:BackendRunStartPattern\s*=\s*'([^']+)'", SOURCE)
if not match:
    raise SystemExit("BackendRunStartPattern declaration was not found")
pattern_text = match.group(1)
pattern = re.compile(pattern_text, re.IGNORECASE)

positives = [
    "--- old start: open-webui.exe serve --port 18080 ---",
    "--- old start: open-webui serve --port 18080 ---",
    r"--- 2026-08-12T18:30:40.0829076+02:00 start: C:\ProgramData\EInfra-OpenWebUI\venv\Scripts\open-webui.exe serve --host 127.0.0.1 --port 18080 ---",
    r'--- 2026-08-12T18:30:40.0829076+02:00 start: "C:\Program Files\EInfra OpenWebUI\open-webui.exe" serve --host 127.0.0.1 --port 18080 ---',
]
negatives = [
    "ERROR function_study_tutor_old",
    r"--- 2026 start: C:\temp\not-open-webui.exe serve --port 18080 ---",
    r"--- 2026 start: C:\temp\open-webui.exe status --port 18080 ---",
    "--- 2026 start: python.exe serve --port 18080 ---",
]
for line in positives:
    if not pattern.search(line):
        raise SystemExit("valid backend run header was rejected: " + line)
for line in negatives:
    if pattern.search(line):
        raise SystemExit("invalid backend run header was accepted: " + line)

def select_latest(lines: list[str], maximum: int = 120) -> list[str]:
    start = -1
    for index, line in enumerate(lines):
        if pattern.search(line):
            start = index
    selected = lines[start:] if start >= 0 else list(lines)
    if len(selected) > maximum:
        if start >= 0 and maximum > 1:
            return [selected[0], *selected[-(maximum - 1):]]
        return selected[-maximum:]
    return selected

tutor = re.compile(r"(study_tutor_|vut_ai_tutor_|function_study_tutor|VUT AI Tutor|STUDY_TUTOR)", re.I)
failure = re.compile(r"(traceback|runtimeerror|importerror|exception|\berror\b|failed|failure)", re.I)
indicates = lambda lines: bool(tutor.search("\n".join(lines)) and failure.search("\n".join(lines)))

unrelated_latest = select_latest([
    positives[0],
    "ERROR function_study_tutor_old",
    positives[1],
    "PermissionError unrelated",
], 20)
if len(unrelated_latest) != 2 or indicates(unrelated_latest):
    raise SystemExit("previous Tutor failure leaked into the newest unrelated run")

tutor_latest = select_latest([
    positives[0],
    "PermissionError unrelated",
    positives[1],
    "RuntimeError function_study_tutor_gateway_bootstrap",
], 20)
if len(tutor_latest) != 2 or not indicates(tutor_latest):
    raise SystemExit("Tutor failure in newest run was not detected")

long_run = [positives[2], *[f"line-{i}" for i in range(50)]]
truncated = select_latest(long_run, 5)
if len(truncated) != 5 or truncated[0] != positives[2] or truncated[-1] != "line-49":
    raise SystemExit("maximum-line truncation did not retain the run header and newest tail")

required_symbols = [
    "function Test-BackendRunStartLine",
    "Test-BackendRunStartLine -Line ([string]$Lines[$index])",
    "Log segmentation self-test selhal pro posledni nesouvisejici beh.",
    "Log segmentation self-test nerozpoznal Tutor chybu v poslednim behu.",
]
missing = [symbol for symbol in required_symbols if symbol not in SOURCE]
if missing:
    raise SystemExit("PowerShell implementation is missing regression symbols: " + repr(missing))

print(json.dumps({
    "ok": True,
    "adapter": "2.1.5",
    "pattern": pattern_text,
    "positive_headers": len(positives),
    "negative_headers": len(negatives),
    "previous_run_isolated": True,
    "latest_tutor_failure_detected": True,
    "truncated_header_retained": True,
}, ensure_ascii=False, sort_keys=True))
