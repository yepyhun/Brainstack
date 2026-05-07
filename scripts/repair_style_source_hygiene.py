#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.style_source_hygiene import run_style_source_hygiene_repair  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair legacy behavior/profile source hygiene for one scope.")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--principal-scope-key", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--explicit-user-request", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    store = BrainstackStore(str(args.db), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        report = run_style_source_hygiene_repair(
            store,
            principal_scope_key=args.principal_scope_key,
            apply=bool(args.apply),
            explicit_user_request=bool(args.explicit_user_request),
            expose_backup_path=True,
        )
    finally:
        store.close()

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if report.get("status") not in {"failed", "rejected"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
