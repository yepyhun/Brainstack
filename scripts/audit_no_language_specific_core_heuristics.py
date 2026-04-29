#!/usr/bin/env python3
"""Fail if Brainstack core contains live-case language patches."""

from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"ExampleNameDative|\\bhívnak\\b|\\bmagyar regex\\b", re.IGNORECASE)


def main() -> int:
    hits: list[str] = []
    for path in (ROOT / "brainstack").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if FORBIDDEN.search(text):
            hits.append(str(path.relative_to(ROOT)))
    if hits:
        print("FAIL language-specific core heuristic hits:")
        print("\n".join(hits))
        return 1
    print("PASS no language-specific core heuristic hits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
