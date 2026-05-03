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

from brainstack import BrainstackMemoryProvider  # noqa: E402
from brainstack.maintenance import MAINTENANCE_CLASS_PERSISTENT_BLOAT  # noqa: E402
from scripts.run_persistent_bloat_soak import PRIVATE_SOAK_SENTINEL, seed_persistent_bloat_soak  # noqa: E402

SCHEMA = "brainstack.persistent_bloat_policy_verifier.v1"


def _provider(tmp: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "m008-bloat-session",
        platform="test",
        user_id="user",
        agent_identity="agent",
        agent_workspace="workspace",
    )
    return provider


def _counts(provider: BrainstackMemoryProvider) -> dict[str, int]:
    store = provider._store
    assert store is not None
    tables = {
        "profile": "profile_items",
        "transcript": "transcript_entries",
        "continuity": "continuity_events",
        "canonical": "canonical_memory_events",
        "receipts": "admission_receipts",
        "conflicts": "graph_conflicts",
        "semantic_index": "semantic_evidence_index",
    }
    output: dict[str, int] = {}
    for key, table in tables.items():
        row = store.conn.execute(f'SELECT COUNT(*) AS count FROM "{table}"').fetchone()
        output[key] = int(row["count"] if row is not None else 0)
    return output


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-m008-bloat-policy-") as tmpdir:
        provider = _provider(Path(tmpdir))
        try:
            store = provider._store
            assert store is not None
            seed_persistent_bloat_soak(store, iterations=8)
            dry_run = json.loads(provider.handle_tool_call("brainstack_consolidate", {"apply": False}))
            before = _counts(provider)
            unsafe_apply = json.loads(
                provider.handle_tool_call(
                    "brainstack_consolidate",
                    {"apply": True, "maintenance_class": MAINTENANCE_CLASS_PERSISTENT_BLOAT},
                )
            )
            after_unsafe = _counts(provider)
            store.upsert_profile_item(
                stable_key="identity:m008:bloat-policy",
                category="identity",
                content="M008 bloat policy semantic index rebuild proof.",
                source="m008-bloat-policy.verifier",
                confidence=0.95,
                metadata=provider._scoped_metadata({"semantic_terms": ["m008 bloat policy"]}),
            )
            store.conn.execute("UPDATE semantic_evidence_index SET fingerprint = 'stale-fingerprint'")
            store.conn.commit()
            semantic_apply = json.loads(
                provider.handle_tool_call("brainstack_consolidate", {"apply": True, "maintenance_class": "semantic_index"})
            )
        finally:
            provider.shutdown()

    rendered = json.dumps({"dry_run": dry_run, "unsafe_apply": unsafe_apply, "semantic_apply": semantic_apply}, ensure_ascii=False, sort_keys=True)
    policy = dry_run.get("dry_run", {}).get("persistent_bloat_policy", [])
    transcript_policy = next((item for item in policy if item.get("lane") == "transcript_continuity"), {})
    semantic_policy = next((item for item in policy if item.get("lane") == "semantic_index"), {})
    durable_policy = next((item for item in policy if item.get("lane") == "durable_truth"), {})
    failures: list[str] = []
    if PRIVATE_SOAK_SENTINEL in rendered:
        failures.append("private_soak_text_leaked")
    if dry_run.get("dry_run", {}).get("persistent_bloat", {}).get("public_safe") is not True:
        failures.append("dry_run_not_public_safe")
    if durable_policy.get("action") != "keep" or durable_policy.get("apply_supported") is not False:
        failures.append("durable_truth_policy_not_preserve_only")
    if transcript_policy.get("apply_supported") is not False:
        failures.append("raw_history_apply_not_rejected")
    if semantic_policy.get("apply_supported") is not True:
        failures.append("semantic_index_rebuild_not_supported")
    if unsafe_apply.get("status") != "rejected":
        failures.append("unsafe_apply_not_rejected")
    if unsafe_apply.get("preservation_contract", {}).get("truth_mutation") is not False:
        failures.append("unsafe_apply_truth_mutation_not_false")
    if before != after_unsafe:
        failures.append("unsafe_apply_mutated_storage")
    if semantic_apply.get("status") != "ok":
        failures.append("semantic_index_apply_not_ok")
    if not semantic_apply.get("changes") or semantic_apply["changes"][0].get("truth_mutation") is not False:
        failures.append("semantic_index_truth_mutation_not_false")
    return {
        "schema": SCHEMA,
        "status": "pass" if not failures else "fail",
        "failure_reasons": failures,
        "policy_summary": {
            "durable_truth": durable_policy,
            "transcript_continuity": transcript_policy,
            "semantic_index": semantic_policy,
        },
        "unsafe_apply": {
            "status": unsafe_apply.get("status"),
            "no_op_reasons": unsafe_apply.get("no_op_reasons"),
            "preservation_contract": unsafe_apply.get("preservation_contract"),
            "storage_unchanged": before == after_unsafe,
        },
        "semantic_index_apply": {
            "status": semantic_apply.get("status"),
            "changes": semantic_apply.get("changes"),
        },
        "public_safe": PRIVATE_SOAK_SENTINEL not in rendered,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify persistent bloat maintenance policy boundaries.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "failure_reasons": report["failure_reasons"]}, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
