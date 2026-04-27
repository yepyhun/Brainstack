#!/usr/bin/env python3
"""Fail on host-language keyword routing for tool guards."""

from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"keresd meg|nyisd meg|open this url|find .*\\.md", re.IGNORECASE)
SCAN_DIRS = (ROOT / "brainstack", ROOT / "scripts")


def main() -> int:
    hits: list[str] = []
    for base in SCAN_DIRS:
        for path in base.rglob("*.py"):
            if path.name.startswith("test_") or "__pycache__" in path.parts:
                continue
            if path.name == "audit_no_tool_keyword_router.py":
                continue
            text = path.read_text(encoding="utf-8")
            if FORBIDDEN.search(text):
                hits.append(str(path.relative_to(ROOT)))
    if hits:
        print("FAIL tool keyword router hits:")
        print("\n".join(hits))
        return 1
    print("PASS no tool keyword router hits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
