from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.db import BrainstackStore
from brainstack.maintenance import MAINTENANCE_CLASS_PERSISTENT_BLOAT, MAINTENANCE_SCHEMA_VERSION
from scripts.run_persistent_bloat_soak import PRIVATE_SOAK_SENTINEL, seed_persistent_bloat_soak


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "bloat-maintenance-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _store(provider: BrainstackMemoryProvider) -> BrainstackStore:
    store = provider._store
    assert store is not None
    return store


def test_maintenance_dry_run_includes_persistent_bloat_policy_without_private_text(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        store = _store(provider)
        seed_persistent_bloat_soak(store, iterations=8)

        receipt = json.loads(provider.handle_tool_call("brainstack_consolidate", {"apply": False}))
    finally:
        provider.shutdown()

    rendered = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
    assert PRIVATE_SOAK_SENTINEL not in rendered
    assert receipt["schema"] == MAINTENANCE_SCHEMA_VERSION
    assert receipt["mode"] == "dry_run"
    assert receipt["dry_run"]["persistent_bloat"]["schema"] == "brainstack.persistent_bloat_report.v1"
    assert receipt["dry_run"]["persistent_bloat"]["public_safe"] is True
    assert any(
        item["maintenance_class"] == MAINTENANCE_CLASS_PERSISTENT_BLOAT
        for item in receipt["dry_run"]["candidates"]
    )
    policy = receipt["dry_run"]["persistent_bloat_policy"]
    assert any(item["lane"] == "durable_truth" and item["action"] == "keep" for item in policy)
    transcript_policy = next(item for item in policy if item["lane"] == "transcript_continuity")
    assert transcript_policy["apply_supported"] is False
    assert "source_ref" in transcript_policy["preserves"]
    conflict_policy = next(item for item in policy if item["lane"] == "graph_conflicts")
    assert "conflict_audit_trail" in conflict_policy["preserves"]


def test_persistent_bloat_apply_is_rejected_without_mutating_truth_or_history(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        store = _store(provider)
        seed_persistent_bloat_soak(store, iterations=8)
        before = {
            "profile": store.conn.execute("SELECT COUNT(*) AS count FROM profile_items").fetchone()["count"],
            "transcript": store.conn.execute("SELECT COUNT(*) AS count FROM transcript_entries").fetchone()["count"],
            "continuity": store.conn.execute("SELECT COUNT(*) AS count FROM continuity_events").fetchone()["count"],
            "canonical": store.conn.execute("SELECT COUNT(*) AS count FROM canonical_memory_events").fetchone()["count"],
            "receipts": store.conn.execute("SELECT COUNT(*) AS count FROM admission_receipts").fetchone()["count"],
            "conflicts": store.conn.execute("SELECT COUNT(*) AS count FROM graph_conflicts").fetchone()["count"],
        }

        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_consolidate",
                {"apply": True, "maintenance_class": MAINTENANCE_CLASS_PERSISTENT_BLOAT},
            )
        )
        after = {
            "profile": store.conn.execute("SELECT COUNT(*) AS count FROM profile_items").fetchone()["count"],
            "transcript": store.conn.execute("SELECT COUNT(*) AS count FROM transcript_entries").fetchone()["count"],
            "continuity": store.conn.execute("SELECT COUNT(*) AS count FROM continuity_events").fetchone()["count"],
            "canonical": store.conn.execute("SELECT COUNT(*) AS count FROM canonical_memory_events").fetchone()["count"],
            "receipts": store.conn.execute("SELECT COUNT(*) AS count FROM admission_receipts").fetchone()["count"],
            "conflicts": store.conn.execute("SELECT COUNT(*) AS count FROM graph_conflicts").fetchone()["count"],
        }
    finally:
        provider.shutdown()

    assert receipt["status"] == "rejected"
    assert "maintenance_class_apply_not_supported" in receipt["no_op_reasons"]
    assert "persistent_bloat_cleanup_requires_explicit_review" in receipt["no_op_reasons"]
    assert receipt["preservation_contract"]["truth_mutation"] is False
    assert receipt["preservation_contract"]["raw_history_mutation"] is False
    assert "receipt" in receipt["preservation_contract"]["preserves"]
    assert "conflict_audit_trail" in receipt["preservation_contract"]["preserves"]
    assert before == after


def test_unsafe_bloat_lane_apply_classes_are_rejected_with_preservation_contract(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        for maintenance_class in ("profile_duplicate_content", "transcript_archive", "graph_conflict_review"):
            receipt = json.loads(
                provider.handle_tool_call(
                    "brainstack_consolidate",
                    {"apply": True, "maintenance_class": maintenance_class},
                )
            )
            assert receipt["status"] == "rejected"
            assert "persistent_bloat_cleanup_requires_explicit_review" in receipt["no_op_reasons"]
            assert receipt["preservation_contract"]["truth_mutation"] is False
    finally:
        provider.shutdown()


def test_semantic_index_apply_still_rebuilds_only_derived_index(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        store = _store(provider)
        store.upsert_profile_item(
            stable_key="identity:bloat-maintenance",
            category="identity",
            content="Maintenance bloat proof record.",
            source="maintenance-test",
            confidence=0.95,
            metadata=provider._scoped_metadata({"semantic_terms": ["bloat maintenance substrate"]}),
        )
        store.conn.execute("UPDATE semantic_evidence_index SET fingerprint = 'stale-fingerprint'")
        store.conn.commit()

        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_consolidate",
                {"apply": True, "maintenance_class": "semantic_index"},
            )
        )
    finally:
        provider.shutdown()

    assert receipt["status"] == "ok"
    assert receipt["changes"][0]["truth_mutation"] is False
    assert receipt["changes"][0]["operation"] == "rebuild_semantic_evidence_index"
    assert receipt["dry_run"]["persistent_bloat"]["public_safe"] is True
