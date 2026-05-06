#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.source_sync_spine import (  # noqa: E402
    DELETION_DEACTIVATE_MISSING,
    SourceSyncConfig,
    build_source_sync_status,
    run_source_sync,
)


def _count(store: BrainstackStore, table: str) -> int:
    return int(store.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def run_probe() -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="brainstack-source-sync-") as temp:
        tmp = Path(temp)
        root = tmp / "docs"
        root.mkdir()
        doc = root / "source.md"
        doc.write_text("# Source\n\nInitial SourceSyncAnchor body.", encoding="utf-8")
        (root / "secret-token.md").write_text("should be skipped", encoding="utf-8")
        store = BrainstackStore(str(tmp / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        try:
            config = SourceSyncConfig(
                source_root=root,
                allow_patterns=("*.md",),
                source_set_id=str(root),
                principal_scope_key="principal:source-sync-verifier",
            )
            first = run_source_sync(store, config)
            second = run_source_sync(store, config)
            doc.write_text("# Source\n\nChanged SourceSyncAnchor body.", encoding="utf-8")
            third = run_source_sync(store, config)
            doc.unlink()
            fourth = run_source_sync(
                store,
                SourceSyncConfig(
                    source_root=root,
                    allow_patterns=("*.md",),
                    source_set_id=str(root),
                    principal_scope_key="principal:source-sync-verifier",
                    deletion_policy=DELETION_DEACTIVATE_MISSING,
                ),
            )
            status = build_source_sync_status(store, principal_scope_key="principal:source-sync-verifier")
            combined = f"{first} {second} {third} {fourth} {status}"

            if first["status"] != "changed" or first["counts"]["inserted"] != 1:
                issues.append({"code": "full_sync_not_inserted"})
            if second["status"] != "unchanged" or second["cursor"] != first["cursor"]:
                issues.append({"code": "unchanged_sync_not_idempotent"})
            if third["status"] != "changed" or third["counts"]["updated"] != 1:
                issues.append({"code": "changed_sync_not_updated"})
            if fourth["counts"]["deactivated"] != 1:
                issues.append({"code": "delete_policy_not_deactivated"})
            if str(root) in combined or "secret-token.md" in combined:
                issues.append({"code": "private_source_leaked"})
            for table in ("admission_receipts", "canonical_memory_events", "graph_relations", "task_items"):
                if _count(store, table) != 0:
                    issues.append({"code": "source_sync_wrote_truth_surface", "table": table})

            return {
                "schema": "brainstack.source_sync_spine_verifier.v1",
                "status": "pass" if not issues else "fail",
                "issues": issues,
                "public_safe": True,
                "full_sync_status": first["status"],
                "unchanged_sync_status": second["status"],
                "changed_sync_status": third["status"],
                "delete_sync_status": fourth["status"],
                "source_set_id": first["source_set_id"],
                "latest_status": status["status"],
                "latest_run_status": status["latest_run"]["status"],
                "truth_authority": status["truth_authority"],
                "raw_private_source_in_status": status["raw_private_source_in_status"],
            }
        finally:
            store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Brainstack SourceSyncSpine behavior.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_probe()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
