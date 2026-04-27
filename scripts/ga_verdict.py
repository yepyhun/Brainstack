#!/usr/bin/env python3
"""Write final GA verdict from dashboard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ga_soak_chaos import final_verdict_from_dashboard, verdict_markdown, write_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dashboard")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    dashboard = json.loads(Path(args.dashboard).read_text(encoding="utf-8"))
    verdict = final_verdict_from_dashboard(dashboard)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(verdict_markdown(verdict), encoding="utf-8")
    write_json(out.with_suffix(".json"), verdict)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
