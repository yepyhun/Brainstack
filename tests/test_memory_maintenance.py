from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.db import BrainstackStore
from brainstack.maintenance import MAINTENANCE_SCHEMA_VERSION


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "maintenance-session",
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


def _seed_stale_semantic_index(provider: BrainstackMemoryProvider) -> None:
    store = _store(provider)
    store.upsert_profile_item(
        stable_key="identity:maintenance",
        category="identity",
        content="Maintenance proof record.",
        source="maintenance-test",
        confidence=0.95,
        metadata=provider._scoped_metadata({"semantic_terms": ["maintenance proof substrate"]}),
    )
    store.conn.execute("UPDATE semantic_evidence_index SET fingerprint = 'stale-fingerprint'")
    store.conn.commit()


def test_consolidate_dry_run_reports_candidates_without_mutating_truth(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        _seed_stale_semantic_index(provider)
        store = _store(provider)
        before = store.get_profile_item(
            stable_key="identity:maintenance",
            principal_scope_key=provider._principal_scope_key,
        )

        receipt = json.loads(provider.handle_tool_call("brainstack_consolidate", {"apply": False}))

        after = store.get_profile_item(
            stable_key="identity:maintenance",
            principal_scope_key=provider._principal_scope_key,
        )
        assert before is not None and after is not None
        assert dict(before) == dict(after)
        assert receipt["schema"] == MAINTENANCE_SCHEMA_VERSION
        assert receipt["mode"] == "dry_run"
        assert receipt["read_only"] is True
        assert any(
            item["maintenance_class"] == "semantic_index" and item["candidate_count"] >= 1
            for item in receipt["dry_run"]["candidates"]
        )
    finally:
        provider.shutdown()


def test_consolidate_apply_rebuilds_only_derived_semantic_index(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        _seed_stale_semantic_index(provider)
        store = _store(provider)
        assert store.semantic_evidence_channel_status()["status"] == "degraded"
        before_profile_count = store.conn.execute(
            "SELECT COUNT(*) AS count FROM profile_items"
        ).fetchone()["count"]

        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_consolidate",
                {"apply": True, "maintenance_class": "semantic_index"},
            )
        )

        after_profile_count = store.conn.execute(
            "SELECT COUNT(*) AS count FROM profile_items"
        ).fetchone()["count"]
        assert receipt["schema"] == MAINTENANCE_SCHEMA_VERSION
        assert receipt["mode"] == "apply"
        assert receipt["status"] == "ok"
        assert receipt["read_only"] is False
        assert receipt["changes"][0]["truth_mutation"] is False
        assert store.semantic_evidence_channel_status()["status"] == "active"
        assert before_profile_count == after_profile_count

        stats = json.loads(provider.handle_tool_call("brainstack_stats", {"strict": False}))
        assert stats["maintenance"]["schema"] == MAINTENANCE_SCHEMA_VERSION
    finally:
        provider.shutdown()


def test_consolidate_rejects_unsupported_apply_class_without_mutation(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        _seed_stale_semantic_index(provider)
        store = _store(provider)
        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_consolidate",
                {"apply": True, "maintenance_class": "profile_duplicate_content"},
            )
        )
        assert receipt["status"] == "rejected"
        assert "maintenance_class_apply_not_supported" in receipt["no_op_reasons"]
        assert store.semantic_evidence_channel_status()["status"] == "degraded"
    finally:
        provider.shutdown()
