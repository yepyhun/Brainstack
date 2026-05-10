from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.db import BrainstackStore
from brainstack.multi_profile_shared_backend import (
    build_multi_profile_support_verdict,
    profile_scope_from_kwargs,
)
from brainstack.shelf_export import export_shelf_bundle
from brainstack.source_sync_spine import SourceSyncConfig, build_source_sync_status, run_source_sync
from tests.test_current_truth_view import _event


def _provider(tmp_path: Path, profile: str) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "shared" / "brainstack.db"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        f"session-{profile}",
        hermes_home=str(tmp_path / "hermes-home"),
        platform="discord",
        user_id="user-public",
        agent_identity=profile,
        agent_workspace="shared-home",
        chat_type="dm",
        chat_id="chat-public",
    )
    return provider


def test_profile_identity_reaches_distinct_principal_scope() -> None:
    scopes = [
        profile_scope_from_kwargs(platform="discord", user_id="user-public", agent_identity=name)
        for name in ("researcher", "coder", "sales")
    ]

    verdict = build_multi_profile_support_verdict(
        profile_scopes=scopes,
        shelf_results={"profile": True, "graph": True, "corpus": True},
    )

    assert len({scope["principal_scope_key"] for scope in scopes}) == 3
    assert verdict["status"] == "certified"
    assert verdict["profile_identity_present"] is True


def test_missing_profile_identity_is_degraded_not_certified() -> None:
    scope = profile_scope_from_kwargs(platform="discord", user_id="user-public")

    verdict = build_multi_profile_support_verdict(profile_scopes=[scope], shelf_results={"profile": True})

    assert verdict["status"] == "degraded"
    assert "missing_profile_identity" in verdict["degraded_reasons"]


def test_behavior_contract_does_not_fallback_across_profiles(tmp_path: Path) -> None:
    researcher = _provider(tmp_path, "researcher")
    try:
        assert researcher._store is not None
        researcher._store.upsert_behavior_contract(
            category="style_contract",
            content="Researcher Contract\n\nRules:\n- Researcher-only behavior rule.",
            source="user_explicit:test",
            confidence=0.99,
            metadata=researcher._scoped_metadata({"source_role": "user"}),
        )
        researcher_scope = researcher._principal_scope_key
    finally:
        researcher.shutdown()

    coder = _provider(tmp_path, "coder")
    try:
        assert coder._store is not None
        assert coder._principal_scope_key != researcher_scope
        assert coder._store.get_behavior_contract(principal_scope_key=coder._principal_scope_key) is None
    finally:
        coder.shutdown()


def test_shelf_export_filters_graph_and_corpus_by_profile_scope(tmp_path: Path) -> None:
    db_path = tmp_path / "brainstack.db"
    store = BrainstackStore(str(db_path), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        scope_a = "platform:test|user_id:user|agent_identity:researcher"
        scope_b = "platform:test|user_id:user|agent_identity:coder"
        store.upsert_graph_state(
            subject_name="Company A",
            attribute="status",
            value_text="researcher-only",
            source="test:graph",
            metadata={"principal_scope_key": scope_a},
        )
        store.upsert_graph_state(
            subject_name="Company B",
            attribute="status",
            value_text="coder-only",
            source="test:graph",
            metadata={"principal_scope_key": scope_b},
        )
        store.ingest_corpus_source(
            {
                "source_adapter": "test",
                "source_id": "doc-a",
                "stable_key": "test:doc-a",
                "title": "Doc A",
                "doc_kind": "note",
                "source_uri": "memory://doc-a",
                "sections": [{"heading": "A", "content": "researcher corpus"}],
                "metadata": {"principal_scope_key": scope_a},
            }
        )
        store.ingest_corpus_source(
            {
                "source_adapter": "test",
                "source_id": "doc-b",
                "stable_key": "test:doc-b",
                "title": "Doc B",
                "doc_kind": "note",
                "source_uri": "memory://doc-b",
                "sections": [{"heading": "B", "content": "coder corpus"}],
                "metadata": {"principal_scope_key": scope_b},
            }
        )

        bundle = export_shelf_bundle(store, shelves=("graph", "corpus"), principal_scope_key=scope_a)
        payload = json.dumps(bundle, ensure_ascii=True)

        assert "researcher-only" in payload
        assert "researcher corpus" in payload
        assert "coder-only" not in payload
        assert "coder corpus" not in payload
    finally:
        store.close()


def test_shared_backend_same_logical_keys_do_not_overwrite_cross_profile_shelves(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.db"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        scope_a = "platform:test|user_id:user|agent_identity:researcher"
        scope_b = "platform:test|user_id:user|agent_identity:coder"
        metadata_a = {"principal_scope_key": scope_a}
        metadata_b = {"principal_scope_key": scope_b}

        store.add_continuity_event(
            session_id="shared-session",
            turn_number=1,
            kind="note",
            content="researcher continuity",
            source="test:continuity",
            metadata=metadata_a,
        )
        store.add_continuity_event(
            session_id="shared-session",
            turn_number=2,
            kind="note",
            content="coder continuity",
            source="test:continuity",
            metadata=metadata_b,
        )
        store.upsert_task_item(
            stable_key="task:same-logical",
            principal_scope_key=scope_a,
            item_type="task",
            title="researcher task",
            due_date="",
            date_scope="none",
            optional=False,
            status="open",
            owner="test",
            source="test:task",
            metadata=metadata_a,
        )
        store.upsert_task_item(
            stable_key="task:same-logical",
            principal_scope_key=scope_b,
            item_type="task",
            title="coder task",
            due_date="",
            date_scope="none",
            optional=False,
            status="open",
            owner="test",
            source="test:task",
            metadata=metadata_b,
        )
        store.upsert_operating_record(
            stable_key="operating:same-logical",
            principal_scope_key=scope_a,
            record_type="active_work",
            content="researcher operating",
            owner="test",
            source="test:operating",
            metadata=metadata_a,
        )
        store.upsert_operating_record(
            stable_key="operating:same-logical",
            principal_scope_key=scope_b,
            record_type="active_work",
            content="coder operating",
            owner="test",
            source="test:operating",
            metadata=metadata_b,
        )
        store.record_canonical_memory_event(_event(event_id="ct_a", principal_scope_key=scope_a))
        store.record_canonical_memory_event(_event(event_id="ct_b", principal_scope_key=scope_b))
        store.ingest_corpus_source(
            {
                "source_adapter": "test",
                "source_id": "same-doc",
                "stable_key": "doc:same-logical",
                "title": "Researcher Doc",
                "doc_kind": "note",
                "source_uri": "memory://same-doc",
                "sections": [{"heading": "A", "content": "researcher corpus same logical"}],
                "metadata": metadata_a,
            }
        )
        store.ingest_corpus_source(
            {
                "source_adapter": "test",
                "source_id": "same-doc",
                "stable_key": "doc:same-logical",
                "title": "Coder Doc",
                "doc_kind": "note",
                "source_uri": "memory://same-doc",
                "sections": [{"heading": "B", "content": "coder corpus same logical"}],
                "metadata": metadata_b,
            }
        )
        store.upsert_proactive_event(
            source="test:proactive",
            kind="proactive_candidate",
            principal_scope_key=scope_a,
            title="researcher proactive",
            summary="researcher only",
        )
        store.upsert_proactive_event(
            source="test:proactive",
            kind="proactive_candidate",
            principal_scope_key=scope_b,
            title="coder proactive",
            summary="coder only",
        )

        source_a = tmp_path / "source-a"
        source_b = tmp_path / "source-b"
        source_a.mkdir()
        source_b.mkdir()
        (source_a / "note.md").write_text("researcher source sync", encoding="utf-8")
        (source_b / "note.md").write_text("coder source sync", encoding="utf-8")
        run_source_sync(
            store,
            SourceSyncConfig(
                source_root=source_a,
                allow_patterns=("*.md",),
                source_set_id="shared-source-set",
                principal_scope_key=scope_a,
            ),
        )
        run_source_sync(
            store,
            SourceSyncConfig(
                source_root=source_b,
                allow_patterns=("*.md",),
                source_set_id="shared-source-set",
                principal_scope_key=scope_b,
            ),
        )

        bundle_a = export_shelf_bundle(
            store,
            shelves=("continuity", "operating", "task", "corpus"),
            principal_scope_key=scope_a,
        )
        payload_a = json.dumps(bundle_a, ensure_ascii=True)
        truth_a = json.dumps(store.get_current_truth_l0_snapshot(principal_scope_key=scope_a), ensure_ascii=True)
        proactive_a = json.dumps(store.list_proactive_items(principal_scope_key=scope_a), ensure_ascii=True)
        source_sync_a = build_source_sync_status(store, source_set_id="shared-source-set", principal_scope_key=scope_a)

        assert "researcher continuity" in payload_a
        assert "coder continuity" not in payload_a
        assert "researcher task" in payload_a
        assert "coder task" not in payload_a
        assert "researcher operating" in payload_a
        assert "coder operating" not in payload_a
        assert "researcher corpus same logical" in payload_a
        assert "coder corpus same logical" not in payload_a
        assert "ct_a" in truth_a
        assert "ct_b" not in truth_a
        assert "researcher proactive" in proactive_a
        assert "coder proactive" not in proactive_a
        assert source_sync_a["status"] == "active"
        assert source_sync_a["active_document_count"] == 1
    finally:
        store.close()
