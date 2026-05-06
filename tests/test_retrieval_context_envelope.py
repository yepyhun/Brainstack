from __future__ import annotations

import json
from pathlib import Path

from brainstack.control_plane import build_working_memory_packet
from brainstack.db import BrainstackStore
from brainstack.source_sync_spine import SourceSyncConfig, run_source_sync
from scripts.verify_projection_semantics_runtime_parity import _brainstack_stats_stale_correction_events


PRINCIPAL_SCOPE = "principal:retrieval-envelope"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _packet(store: BrainstackStore, query: str, **signals: object) -> dict:
    return build_working_memory_packet(
        store,
        query=query,
        session_id="session:retrieval-envelope",
        principal_scope_key=PRINCIPAL_SCOPE,
        profile_match_limit=2,
        continuity_recent_limit=2,
        continuity_match_limit=2,
        transcript_match_limit=2,
        transcript_char_budget=400,
        evidence_item_budget=4,
        graph_limit=2,
        corpus_limit=2,
        corpus_char_budget=400,
        record_retrievals=False,
        adaptive_route_signals=dict(signals),
    )


def test_retrieval_context_envelope_marks_current_truth_and_stale_support(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        for event in _brainstack_stats_stale_correction_events():
            copied = json.loads(json.dumps(event))
            copied.setdefault("scope", {})["principal_scope_key"] = PRINCIPAL_SCOPE
            store.record_canonical_memory_event(copied)

        packet = _packet(store, "structured current truth request", required_evidence_classes=["current_truth"])
        envelope = packet["retrieval_context_envelope"]

        assert envelope["schema"] == "brainstack.retrieval_context_envelope.v1"
        assert envelope["route_class"] == "current_truth"
        assert envelope["active_scope"]["kind"] == "principal_scoped"
        assert envelope["active_scope"]["scope_hash"]
        assert PRINCIPAL_SCOPE not in str(envelope)
        assert envelope["evidence_counts"]["current_truth"] == 1
        assert envelope["evidence_counts"]["support_only"] >= 1
        assert envelope["evidence_counts"]["stale_prior_conflict"] == 1
        assert envelope["freshness"]["ordinary_hot_path_rebuild"] is False
        assert envelope["public_safe"] is True
        assert "## Brainstack Retrieval Context" in packet["block"]
        assert "current_truth=1" in packet["block"]
    finally:
        store.close()


def test_retrieval_context_envelope_exposes_source_sync_expand_handles_without_private_path(tmp_path: Path) -> None:
    root = tmp_path / "private-docs"
    root.mkdir()
    (root / "source.md").write_text("# Source\n\nRetrievalEnvelopeSourceSyncAnchor lives here.", encoding="utf-8")
    store = _open_store(tmp_path)
    try:
        run_source_sync(
            store,
            SourceSyncConfig(
                source_root=root,
                allow_patterns=("*.md",),
                source_set_id=str(root),
                principal_scope_key=PRINCIPAL_SCOPE,
            ),
        )
        packet = _packet(store, "RetrievalEnvelopeSourceSyncAnchor", required_evidence_classes=["corpus"])
        envelope = packet["retrieval_context_envelope"]
        combined = f"{packet['block']} {envelope}"

        assert envelope["route_class"] == "corpus"
        assert envelope["evidence_counts"]["corpus"] == 1
        assert envelope["source_sync"]["selected"] == 1
        assert envelope["source_sync"]["expand_handles"] == 1
        assert "source_expand_handles=1" in packet["block"]
        assert str(root) not in combined
        assert "private-docs" not in combined
    finally:
        store.close()


def test_retrieval_context_envelope_keeps_no_memory_route_bounded(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        packet = _packet(store, "", memory_intent="none")
        envelope = packet["retrieval_context_envelope"]

        assert envelope["route_class"] == "no_memory_minimal"
        assert envelope["semantic_retrieval"]["enabled"] is False
        assert envelope["semantic_retrieval"]["limit"] == 0
        assert envelope["evidence_counts"]["current_truth"] == 0
        assert envelope["public_safe"] is True
        assert "semantic=skipped" in packet["block"]
    finally:
        store.close()
