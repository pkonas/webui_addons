#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted(ROOT.rglob("*.ps1"))
PAIRS = {"(": ")", "[": "]", "{": "}"}
CLOSERS = {value: key for key, value in PAIRS.items()}
COMMON = {
    "verbose", "debug", "erroraction", "warningaction", "informationaction",
    "progressaction", "errorvariable", "warningvariable", "informationvariable",
    "outvariable", "outbuffer", "pipelinevariable", "whatif", "confirm",
}
SCOPES = {"global", "local", "script", "private", "using", "env", "function", "variable", "alias"}


def validate(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    stack: list[tuple[str, int, int]] = []
    state = "normal"
    here_end = ""
    line = 1
    column = 1
    index = 0
    here_strings = 0
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if state.startswith("here_"):
            line_start = index == 0 or text[index - 1] == "\n"
            if line_start and text.startswith(here_end, index):
                after = index + 2
                if after == len(text) or text[after] == "\n":
                    index += 2; column += 2; state = "normal"; here_end = ""; continue
            if char == "\n": line += 1; column = 1
            else: column += 1
            index += 1; continue
        if state == "line_comment":
            if char == "\n": state = "normal"; line += 1; column = 1
            else: column += 1
            index += 1; continue
        if state == "block_comment":
            if char == "#" and nxt == ">": state = "normal"; index += 2; column += 2; continue
            if char == "\n": line += 1; column = 1
            else: column += 1
            index += 1; continue
        if state == "single":
            if char == "'" and nxt == "'": index += 2; column += 2; continue
            if char == "'": state = "normal"
            if char == "\n": raise ValueError(f"unterminated single quote before {line}")
            index += 1; column += 1; continue
        if state == "double":
            if char == "`": index += 2; column += 2; continue
            if char == '"' and nxt == '"': index += 2; column += 2; continue
            if char == '"': state = "normal"
            if char == "\n": raise ValueError(f"unterminated double quote before {line}")
            index += 1; column += 1; continue
        if char == "<" and nxt == "#": state = "block_comment"; index += 2; column += 2; continue
        if char == "#": state = "line_comment"; index += 1; column += 1; continue
        if char == "`": index += 2; column += 2; continue
        if char == "@" and nxt in {"'", '"'}:
            end = index + 2
            while end < len(text) and text[end] in " \t": end += 1
            if end < len(text) and text[end] == "\n":
                state = "here_single" if nxt == "'" else "here_double"
                here_end = "'@" if nxt == "'" else '"@'
                here_strings += 1; index = end + 1; line += 1; column = 1; continue
        if char == "'": state = "single"; index += 1; column += 1; continue
        if char == '"': state = "double"; index += 1; column += 1; continue
        if char in PAIRS: stack.append((char, line, column))
        elif char in CLOSERS:
            if not stack or stack[-1][0] != CLOSERS[char]: raise ValueError(f"unexpected {char} at {line}:{column}")
            stack.pop()
        if char == "\n": line += 1; column = 1
        else: column += 1
        index += 1
    if state != "normal": raise ValueError(f"unterminated lexical state {state}")
    if stack: raise ValueError(f"unclosed {stack[-1][0]} from {stack[-1][1]}:{stack[-1][2]}")

    has_cmdlet_binding = bool(re.search(r"(?i)\[\s*CmdletBinding\s*\(", text))
    params = [item.lower() for item in re.findall(r"(?m)(?<![A-Za-z0-9_])\$([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|,|\))", text)]
    duplicate_params = sorted({name for name in params if params.count(name) > 1})
    collisions = sorted(set(params) & COMMON) if has_cmdlet_binding else []
    unsafe_colons = []
    for match in re.finditer(r"\$([A-Za-z_][A-Za-z0-9_]*)\:", text):
        if match.group(1).lower() not in SCOPES:
            unsafe_colons.append(match.group(0))
    if collisions:
        raise ValueError(f"CmdletBinding common-parameter collisions: {collisions}")
    if unsafe_colons:
        raise ValueError(f"unsafe variable-colon interpolation: {unsafe_colons[:5]}")
    return {"lines": line, "here_strings": here_strings, "duplicate_parameter_candidates": len(duplicate_params)}


results = {str(path.relative_to(ROOT)): validate(path) for path in FILES}
print(json.dumps({"ok": True, "powershell_files": len(FILES), "files": results}, sort_keys=True))
