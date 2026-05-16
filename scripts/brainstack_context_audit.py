#!/usr/bin/env python3
"""Public-safe Hermes session context accounting CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from brainstack.compression_pressure import classify_compression_pressure  # noqa: E402
from brainstack.runtime_context_accounting import (  # noqa: E402
    build_context_accounting_report,
    newest_session_paths,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions-dir", type=Path, required=True)
    parser.add_argument("--log-file", type=Path)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    log_text = ""
    if args.log_file and args.log_file.exists():
        log_text = args.log_file.read_text(encoding="utf-8", errors="replace")
    report = build_context_accounting_report(
        newest_session_paths(args.sessions_dir, limit=args.limit),
        log_text=log_text,
    )
    report["compression_pressure"] = classify_compression_pressure(report).to_dict()
    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
