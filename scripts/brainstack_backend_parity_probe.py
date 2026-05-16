#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.diagnostics import build_backend_parity_probe  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a public-safe Brainstack backend parity probe.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--graph-backend", default="sqlite")
    parser.add_argument("--graph-db-path", default="")
    parser.add_argument("--corpus-backend", default="sqlite")
    parser.add_argument("--corpus-db-path", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--session-id", default="backend-parity-probe")
    parser.add_argument("--principal-scope-key", default="")
    args = parser.parse_args()

    store = BrainstackStore(
        args.db_path,
        graph_backend=args.graph_backend,
        graph_db_path=args.graph_db_path or None,
        corpus_backend=args.corpus_backend,
        corpus_db_path=args.corpus_db_path or None,
    )
    store.open()
    try:
        report = build_backend_parity_probe(
            store,
            query=args.query,
            session_id=args.session_id,
            principal_scope_key=args.principal_scope_key,
        )
    finally:
        store.close()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
