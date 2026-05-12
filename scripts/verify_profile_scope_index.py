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


def build_report(*, principal_count: int = 1000) -> dict:
    with tempfile.TemporaryDirectory(prefix="brainstack-profile-scope-index-") as tmp:
        store = BrainstackStore(str(Path(tmp) / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        try:
            for index in range(principal_count):
                scope_key = f"principal:{index:04d}"
                store.upsert_profile_item(
                    stable_key="style.reply_tone",
                    category="style_preference",
                    content=f"Scoped style for {scope_key}",
                    source="user_explicit",
                    confidence=0.9,
                    metadata={
                        "principal_scope_key": scope_key,
                        "memory_write_receipt_id": f"receipt:{index:04d}",
                    },
                )
            target_scope = f"principal:{principal_count // 2:04d}"
            store.reset_profile_scope_lookup_diagnostics()
            item = store.get_profile_item(stable_key="style.reply_tone", principal_scope_key=target_scope)
            diagnostics = store.profile_scope_lookup_diagnostics()
            plan = store.conn.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT id
                FROM profile_items
                WHERE active = 1 AND logical_stable_key = ? AND principal_scope_key = ?
                ORDER BY confidence DESC, updated_at DESC, id DESC
                LIMIT 1
                """,
                ("style.reply_tone", target_scope),
            ).fetchall()
            plan_text = " ".join(str(column) for row in plan for column in tuple(row))
            failure_reasons: list[str] = []
            if not item or item.get("content") != f"Scoped style for {target_scope}":
                failure_reasons.append("wrong_principal_result")
            if diagnostics["like_fallback_count"] != 0:
                failure_reasons.append("like_fallback_used")
            if diagnostics["exact_storage_fallback_count"] != 0:
                failure_reasons.append("exact_storage_fallback_used")
            if "idx_profile_scope_lookup" not in plan_text:
                failure_reasons.append("indexed_plan_missing")
            return {
                "schema": "brainstack.profile_scope_index_verifier.v1",
                "status": "pass" if not failure_reasons else "fail",
                "failure_reasons": failure_reasons,
                "principal_count": principal_count,
                "target_scope": target_scope,
                "diagnostics": diagnostics,
                "indexed_query_plan": plan_text,
            }
        finally:
            store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Brainstack indexed profile-scope lookup.")
    parser.add_argument("--out", type=Path, required=True, help="Path to write the public-safe JSON report.")
    parser.add_argument("--principal-count", type=int, default=1000)
    args = parser.parse_args()
    report = build_report(principal_count=max(args.principal_count, 1))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
