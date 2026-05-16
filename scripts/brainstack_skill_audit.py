#!/usr/bin/env python3
"""Audit SKILL.md entrypoints for progressive-disclosure readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from brainstack.skill_runtime_audit import audit_skill_files  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--oversized-chars", type=int, default=8_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_skill_files(args.roots, oversized_chars=args.oversized_chars)
    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0 if report["verdict"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
