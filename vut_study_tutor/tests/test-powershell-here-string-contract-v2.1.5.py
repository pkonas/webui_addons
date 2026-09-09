#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PS_FILES = sorted(path for path in ROOT.rglob("*.ps1") if "reference" not in path.parts)
errors: list[str] = []
checked_here_strings = 0
for path in PS_FILES:
    lines = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").split("\n")
    active: str | None = None
    opening_line = 0
    for number, line in enumerate(lines, 1):
        if active is None:
            stripped = line.rstrip()
            if stripped.endswith("@'"):
                active = "'@"
                opening_line = number
                checked_here_strings += 1
            elif stripped.endswith('@"'):
                active = '"@'
                opening_line = number
                checked_here_strings += 1
            continue
        if line == active:
            active = None
            opening_line = 0
        elif line.lstrip() == active and line != active:
            errors.append(
                f"{path.relative_to(ROOT)}:{number}: here-string terminator is indented"
            )
    if active is not None:
        errors.append(
            f"{path.relative_to(ROOT)}:{opening_line}: unterminated here-string {active}"
        )
if errors:
    raise SystemExit("PowerShell here-string contract failed: " + repr(errors))
print(json.dumps({
    "ok": True,
    "powershell_files": len(PS_FILES),
    "here_strings": checked_here_strings,
    "indented_terminators": 0,
    "unterminated_here_strings": 0,
}, ensure_ascii=True, sort_keys=True))
