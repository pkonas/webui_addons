#!/usr/bin/env python3
from __future__ import annotations

import json
import platform
import sys

MINIMUM = (3, 11)
version = tuple(int(value) for value in sys.version_info[:3])
ok = version >= MINIMUM
result = {
    "ok": ok,
    "version": ".".join(map(str, version)),
    "implementation": platform.python_implementation(),
    "executable": sys.executable,
    "minimum": ".".join(map(str, MINIMUM)),
}
print(json.dumps(result, ensure_ascii=True, sort_keys=True))
raise SystemExit(0 if ok else 3)
