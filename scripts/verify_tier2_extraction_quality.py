#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.tier2_extraction_quality import (  # noqa: E402
    build_tier2_extraction_quality_report,
    report_to_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify donor-aligned Tier2 extraction quality on public-safe fixtures.")
    parser.add_argument("--out", type=Path, help="Optional path to write the JSON proof report.")
    args = parser.parse_args()

    report = build_tier2_extraction_quality_report()
    text = report_to_json(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report.get("status") == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
