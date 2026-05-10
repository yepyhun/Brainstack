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
from brainstack.source_integrity import (  # noqa: E402
    build_source_integrity_envelope,
    is_source_backed_truth_answerable,
    public_source_integrity_status,
    verify_source_integrity_transition,
)
from brainstack.source_sync_spine import SourceSyncConfig, run_source_sync  # noqa: E402


def _count(store: BrainstackStore, table: str) -> int:
    return int(store.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def build_report() -> dict[str, Any]:
    issues: list[str] = []
    with tempfile.TemporaryDirectory(prefix="brainstack-source-integrity-") as temp:
        tmp = Path(temp)
        root = tmp / "docs"
        root.mkdir()
        doc = root / "source.md"
        doc.write_text("# Source\n\nInitial source integrity body.", encoding="utf-8")
        store = BrainstackStore(str(tmp / "brainstack.db"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        try:
            config = SourceSyncConfig(
                source_root=root,
                allow_patterns=("*.md",),
                source_set_id="public-source-integrity-fixture",
                principal_scope_key="principal:source-integrity",
            )
            first = run_source_sync(store, config)
            first_meta_row = store.conn.execute(
                "SELECT metadata_json FROM corpus_documents WHERE active = 1 LIMIT 1"
            ).fetchone()
            first_meta = json.loads(str(first_meta_row["metadata_json"] or "{}"))
            first_integrity = first_meta["source_sync_spine"]["source_integrity"]

            doc.write_text("# Source\n\nChanged source integrity body.", encoding="utf-8")
            second = run_source_sync(store, config)
            second_meta_row = store.conn.execute(
                "SELECT metadata_json FROM corpus_documents WHERE active = 1 LIMIT 1"
            ).fetchone()
            second_meta = json.loads(str(second_meta_row["metadata_json"] or "{}"))
            second_integrity = second_meta["source_sync_spine"]["source_integrity"]

            previous = build_source_integrity_envelope(
                source_handle=first_meta["source_sync_spine"]["source_handle"],
                source_adapter="source_sync_local",
                source_scope="principal:source-integrity",
                content_hash=first_meta["source_sync_spine"]["content_hash"],
                receipt_id="receipt:old",
                truth_eligible=True,
            )
            current = build_source_integrity_envelope(
                source_handle=second_meta["source_sync_spine"]["source_handle"],
                source_adapter="source_sync_local",
                source_scope="principal:source-integrity",
                content_hash=second_meta["source_sync_spine"]["content_hash"],
                truth_eligible=True,
            )
            transition = verify_source_integrity_transition(previous=previous, current=current)
            missing = build_source_integrity_envelope(
                source_handle="source:missing",
                source_adapter="source_sync_local",
                source_scope="principal:source-integrity",
                content_hash="",
                receipt_id="receipt:missing",
                truth_eligible=True,
            )
            public_status = public_source_integrity_status(previous)

            proof = {
                "source_sync_attaches_integrity_envelope": first_integrity["schema"]
                == "brainstack.source_integrity_public_status.v1",
                "source_update_does_not_write_truth": all(
                    _count(store, table) == 0
                    for table in ("admission_receipts", "canonical_memory_events", "graph_relations", "task_items")
                ),
                "drift_blocks_truth_until_readmission": transition["reason_code"]
                == "SOURCE_DRIFT_REQUIRES_READMISSION"
                and transition["durable_truth_mutation_allowed"] is False,
                "missing_fingerprint_not_answerable": is_source_backed_truth_answerable(missing) is False,
                "agent_facing_status_public_safe": public_status["raw_private_source_in_status"] is False
                and str(root) not in str(public_status),
                "source_sync_second_run_changed": second["status"] == "changed",
            }
            issues = [key for key, value in proof.items() if value is not True]
            return {
                "schema": "brainstack.source_integrity_spine_verifier.v1",
                "status": "pass" if not issues else "fail",
                "public_safe": True,
                "llm_calls_performed": False,
                "issues": issues,
                "proof": proof,
                "first_sync_status": first["status"],
                "second_sync_status": second["status"],
                "first_integrity_status": first_integrity["status"],
                "second_integrity_status": second_integrity["status"],
                "transition_reason_code": transition["reason_code"],
            }
        finally:
            store.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_report()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("schema", "status", "issues")}, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
