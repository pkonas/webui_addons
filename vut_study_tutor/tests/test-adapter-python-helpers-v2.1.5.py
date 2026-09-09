#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1"
TEXT = INSTALLER.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def extract(variable: str) -> str:
    pattern = re.compile(
        rf"(?m)^\s*\${re.escape(variable)}\s*=\s*@'\n(?P<code>.*?)\n'@\s*$",
        re.S,
    )
    match = pattern.search(TEXT)
    if not match:
        raise SystemExit(f"could not extract PowerShell here-string ${variable}")
    return match.group("code") + "\n"


with tempfile.TemporaryDirectory(prefix="vut-einfra-helper-test-") as temp_name:
    temp = Path(temp_name)
    database = temp / "webui.db"
    backup = temp / "backup"
    result_path = temp / "result.json"
    scripts = {
        "init": extract("initSource"),
        "offline": extract("pythonSource"),
        "verify": extract("verifySource"),
    }
    paths: dict[str, Path] = {}
    for name, source in scripts.items():
        path = temp / f"{name}.py"
        path.write_text(source, encoding="utf-8")
        compile(source, str(path), "exec")
        paths[name] = path

    init = subprocess.run(
        [sys.executable, str(paths["init"]), str(database)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if init.returncode != 0:
        raise SystemExit("init helper failed: " + init.stderr)

    offline = subprocess.run(
        [
            sys.executable,
            str(paths["offline"]),
            str(database),
            str(backup),
            str(result_path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if offline.returncode != 0:
        raise SystemExit("offline helper failed: " + offline.stderr)
    if not result_path.is_file():
        raise SystemExit("offline helper did not create its result file")
    report = json.loads(result_path.read_text(encoding="utf-8"))
    if report.get("updated_count") != 2 or not report.get("ok"):
        raise SystemExit("offline helper changed an unexpected number of rows")
    backup_path = Path(report["backup"])
    if not backup_path.is_file() or backup_path.stat().st_size <= 0:
        raise SystemExit("offline helper did not create a valid SQLite backup")

    verify = subprocess.run(
        [sys.executable, str(paths["verify"]), str(database)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if verify.returncode != 0:
        raise SystemExit("verify helper rejected the recovered database: " + verify.stderr)

print(json.dumps({
    "ok": True,
    "adapter": "2.1.5",
    "file_based_helpers_executed": ["init", "offline", "verify"],
    "updated_count": 2,
    "unrelated_function_preserved": True,
    "sqlite_backup_verified": True,
}, ensure_ascii=True, sort_keys=True))
