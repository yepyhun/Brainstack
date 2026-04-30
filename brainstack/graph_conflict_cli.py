"""Operator-only graph conflict resolution CLI module."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .db import BrainstackStore


def default_db_path() -> Path:
    hermes_home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()
    return hermes_home / "brainstack" / "brainstack.db"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--conflict-id", type=int, required=True)
    parser.add_argument(
        "--decision",
        choices=["accept_current", "accept_candidate", "quarantine_candidate", "supersede_with_new_value"],
        required=True,
    )
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--new-value-text", default="")
    parser.add_argument("--evidence-ref", action="append", default=[])
    args = parser.parse_args()

    store = BrainstackStore(str(args.db), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        result = store.resolve_graph_conflict(
            conflict_id=args.conflict_id,
            decision=args.decision,
            approved_by=args.approved_by,
            reason=args.reason,
            evidence_refs=list(args.evidence_ref or []),
            new_value_text=args.new_value_text,
        )
    finally:
        store.close()

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
