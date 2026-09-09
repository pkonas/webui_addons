#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted(path for path in ROOT.rglob("*.ps1") if "reference" not in path.parts)
PAIRS = {"(": ")", "[": "]", "{": "}"}
CLOSERS = {value: key for key, value in PAIRS.items()}


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
                    index += 2
                    column += 2
                    state = "normal"
                    here_end = ""
                    continue
            if char == "\n":
                line += 1
                column = 1
            else:
                column += 1
            index += 1
            continue

        if state == "line_comment":
            if char == "\n":
                state = "normal"
                line += 1
                column = 1
            else:
                column += 1
            index += 1
            continue

        if state == "block_comment":
            if char == "#" and nxt == ">":
                state = "normal"
                index += 2
                column += 2
                continue
            if char == "\n":
                line += 1
                column = 1
            else:
                column += 1
            index += 1
            continue

        if state == "single":
            if char == "'" and nxt == "'":
                index += 2
                column += 2
                continue
            if char == "'":
                state = "normal"
            if char == "\n":
                raise ValueError(f"unterminated single-quoted string before line {line}")
            index += 1
            column += 1
            continue

        if state == "double":
            if char == "`":
                if nxt == "\n":
                    line += 1
                    column = 1
                else:
                    column += 2
                index += 2
                continue
            if char == '"' and nxt == '"':
                index += 2
                column += 2
                continue
            if char == '"':
                state = "normal"
            if char == "\n":
                # Expandable strings can be continued only via a trailing backtick,
                # which is handled above.
                raise ValueError(f"unterminated double-quoted string before line {line}")
            index += 1
            column += 1
            continue

        # Normal state.
        if char == "<" and nxt == "#":
            state = "block_comment"
            index += 2
            column += 2
            continue
        if char == "#":
            state = "line_comment"
            index += 1
            column += 1
            continue
        if char == "`":
            if nxt == "\n":
                line += 1
                column = 1
            else:
                column += 2
            index += 2
            continue
        if char == "@" and nxt in {"'", '"'}:
            end = index + 2
            while end < len(text) and text[end] in " \t":
                end += 1
            if end < len(text) and text[end] == "\n":
                state = "here_single" if nxt == "'" else "here_double"
                here_end = "'@" if nxt == "'" else '"@'
                here_strings += 1
                index = end + 1
                line += 1
                column = 1
                continue
        if char == "'":
            state = "single"
            index += 1
            column += 1
            continue
        if char == '"':
            state = "double"
            index += 1
            column += 1
            continue
        if char in PAIRS:
            stack.append((char, line, column))
        elif char in CLOSERS:
            if not stack or stack[-1][0] != CLOSERS[char]:
                raise ValueError(f"unexpected {char!r} at {line}:{column}")
            stack.pop()
        if char == "\n":
            line += 1
            column = 1
        else:
            column += 1
        index += 1

    if state != "normal":
        raise ValueError(f"unterminated lexical state {state}")
    if stack:
        opener, open_line, open_column = stack[-1]
        raise ValueError(f"unclosed {opener!r} from {open_line}:{open_column}")
    return {"here_strings": here_strings, "lines": line}


results = {}
for path in FILES:
    try:
        results[str(path.relative_to(ROOT))] = validate(path)
    except ValueError as exc:
        raise SystemExit(f"PowerShell lexical validation failed for {path.relative_to(ROOT)}: {exc}") from exc
print(json.dumps({
    "ok": True,
    "powershell_files": len(FILES),
    "files": results,
}, ensure_ascii=True, sort_keys=True))
