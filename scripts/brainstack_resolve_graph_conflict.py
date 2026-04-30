#!/usr/bin/env python3
"""Operator-only graph conflict resolution CLI."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from brainstack.graph_conflict_cli import main as module_main

    return module_main()


if __name__ == "__main__":
    raise SystemExit(main())
