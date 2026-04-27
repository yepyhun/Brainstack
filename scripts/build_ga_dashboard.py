#!/usr/bin/env python3
"""Build final GA dashboard from current automated evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_ga_dashboard_sample import sample_probes  # noqa: E402
from scripts.ga_dashboard import build_ga_dashboard  # noqa: E402
from scripts.ga_soak_chaos import write_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    write_json(Path(args.out), build_ga_dashboard(sample_probes()))
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
