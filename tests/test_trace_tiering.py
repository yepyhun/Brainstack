from __future__ import annotations

from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.trace_tiering import build_compact_query_trace, validate_compact_query_trace_public_safety


def _store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def test_compact_query_trace_omits_raw_evidence_but_keeps_diagnostics(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.upsert_profile_item(
            stable_key="identity:m008:trace",
            category="identity",
            content="M008 trace tier profile evidence.",
            source="trace-tier.fixture",
            confidence=0.99,
            metadata={"principal_scope_key": "principal:m008:trace", "truth_eligible": True},
        )

        full = build_query_inspect(
            store,
            query="trace tier profile",
            session_id="session:m008:trace",
            principal_scope_key="principal:m008:trace",
        )
        compact = build_compact_query_trace(full)

        assert full["trace_mode"] == "full"
        assert full["compact_trace_available"] is True
        assert compact["schema"] == "brainstack.compact_query_trace.v1"
        assert compact["trace_mode"] == "compact"
        assert compact["full_trace_available"] is True
        assert compact["selected_counts"]["profile"] >= 1
        assert compact["final_packet"]["diagnostic_evidence_count"] >= 1
        assert "preview" not in compact["final_packet"]
        assert validate_compact_query_trace_public_safety(compact) == []
    finally:
        store.close()


def test_build_query_inspect_can_return_compact_trace_directly(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        compact = build_query_inspect(
            store,
            query="compact trace no memory",
            session_id="session:m008:trace:compact",
            principal_scope_key="principal:m008:trace",
            trace_mode="compact",
        )

        assert compact["schema"] == "brainstack.compact_query_trace.v1"
        assert compact["trace_mode"] == "compact"
        assert "selected_evidence" not in compact
        assert "suppressed_evidence" not in compact
        assert validate_compact_query_trace_public_safety(compact) == []
    finally:
        store.close()
