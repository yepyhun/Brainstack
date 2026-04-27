#!/usr/bin/env python3
"""Audit and optionally demote assistant-output contamination candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.product_contracts import audit_contamination_candidates, dump_json  # noqa: E402


def load_claims(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(item) for item in payload]
    return [dict(item) for item in payload.get("claims", [])]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()

    audit = audit_contamination_candidates(load_claims(Path(args.db)))
    if args.out:
        dump_json(Path(args.out), audit)
    print(json.dumps({"audit_only": args.audit_only, "suspect_count": audit["suspect_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
