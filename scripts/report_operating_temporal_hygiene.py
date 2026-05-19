#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.operating_temporal_report import build_operating_temporal_hygiene_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a public-safe operating temporal hygiene dry-run report.")
    parser.add_argument("--db", required=True, type=Path, help="Brainstack SQLite database path.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum dry-run candidates to include.")
    args = parser.parse_args()

    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row
    try:
        report = build_operating_temporal_hygiene_report(conn, limit=args.limit)
    finally:
        conn.close()
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
