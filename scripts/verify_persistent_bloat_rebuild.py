#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.persistent_bloat_rebuild import verify_persistent_bloat_rebuild  # noqa: E402
from scripts.run_persistent_bloat_soak import seed_persistent_bloat_soak  # noqa: E402


def build_report(*, db_path: Path | None = None, iterations: int = 24) -> dict[str, object]:
    path = Path(db_path) if db_path is not None else Path(tempfile.mkdtemp()) / "persistent-bloat-rebuild.sqlite3"
    if path.exists():
        path.unlink()
    store = BrainstackStore(str(path))
    store.open()
    try:
        seed_counts = seed_persistent_bloat_soak(store, iterations=iterations)
        proof = verify_persistent_bloat_rebuild(store, limit=max(2000, iterations * 4))
    finally:
        store.close()
    return {
        "schema": "brainstack.persistent_bloat_rebuild_cli.v1",
        "status": proof.get("status"),
        "public_safe": proof.get("public_safe"),
        "db_path": str(path),
        "seed_counts": seed_counts,
        "proof": proof,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify persistent bloat maintenance does not alter projection answerability.")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--iterations", type=int, default=24)
    args = parser.parse_args()
    payload = build_report(db_path=args.db, iterations=args.iterations)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    print(
        json.dumps(
            {
                "schema": payload["schema"],
                "status": payload["status"],
                "public_safe": payload["public_safe"],
                "issues": payload["proof"].get("issues") if isinstance(payload.get("proof"), dict) else [],
                "critical_counters": payload["proof"].get("critical_counters") if isinstance(payload.get("proof"), dict) else {},
                "seed_counts": payload["seed_counts"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
