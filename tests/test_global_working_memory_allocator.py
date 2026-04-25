from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.working_memory_allocator import build_global_allocator_shadow


PRINCIPAL_SCOPE = "principal:global-allocator"


def _candidate(
    key: str,
    *,
    shelf: str,
    status: str = "selected",
    tokens: int = 10,
    authority_floor: bool = False,
    rrf: float = 0.0,
) -> dict:
    return {
        "schema": "brainstack.retrieval_candidate.v1",
        "candidate_id": key,
        "evidence_key": f"{shelf}:{key}",
        "shelf": shelf,
        "selection": {"status": status, "reason": "fixture", "suppression_reason": ""},
        "source": {"retrieval_source": "fixture", "match_mode": "fixture", "channels": [], "channel_ranks": {}},
        "authority": {"floor": 100 if authority_floor else 0, "floor_applied": authority_floor, "level": ""},
        "score": {"rrf": rrf, "keyword": 0.0, "semantic": 0.0, "query_token_overlap": 0, "query_token_count": 0},
        "cost": {"preview_char_count": tokens * 4, "preview_token_estimate": tokens},
        "modality": {"primary": "text", "metadata_ready": True},
        "donor_metadata": {"brainstack": {"record_type": "fixture"}},
    }


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def test_global_allocator_keeps_authority_floor_before_token_savings() -> None:
    trace = {
        "schema": "brainstack.retrieval_candidate_trace.v1",
        "selected": [
            _candidate("low-a", shelf="transcript", tokens=20, rrf=0.8),
            _candidate("must-keep", shelf="graph", tokens=30, authority_floor=True, rrf=0.1),
            _candidate("low-b", shelf="corpus", tokens=25, rrf=0.7),
        ],
        "suppressed": [_candidate("suppressed-a", shelf="continuity_match", status="suppressed", tokens=5, rrf=0.9)],
    }

    report = build_global_allocator_shadow(trace, candidate_budget=1)

    assert report["schema"] == "brainstack.global_allocator_shadow.v1"
    assert report["mode"] == "shadow_read_only"
    assert report["authority_floor_verdict"] == "pass"
    assert [row["candidate_id"] for row in report["selected"]] == ["must-keep"]
    assert any(row["candidate_id"] == "low-a" for row in report["cut"])
    assert report["preview_token_delta"] < 0


def test_global_allocator_reports_over_budget_authority_floor_instead_of_cutting() -> None:
    trace = {
        "schema": "brainstack.retrieval_candidate_trace.v1",
        "selected": [
            _candidate("must-a", shelf="operating", authority_floor=True),
            _candidate("must-b", shelf="graph", authority_floor=True),
        ],
        "suppressed": [],
    }

    report = build_global_allocator_shadow(trace, candidate_budget=1)

    assert report["authority_floor_verdict"] == "over_budget_due_to_authority_floor"
    assert {row["candidate_id"] for row in report["selected"]} == {"must-a", "must-b"}


def test_global_allocator_disabled_mode_is_explicit_rollback_path() -> None:
    report = build_global_allocator_shadow(
        {"schema": "brainstack.retrieval_candidate_trace.v1", "selected": [], "suppressed": []},
        candidate_budget=4,
        enabled=False,
    )

    assert report["mode"] == "disabled"
    assert report["reason_codes"] == ["allocator_disabled"]
    assert report["selected"] == []


def test_global_allocator_operation_guard_bounds_shadow_work() -> None:
    trace = {
        "schema": "brainstack.retrieval_candidate_trace.v1",
        "selected": [_candidate(f"sel-{index}", shelf="transcript", tokens=1) for index in range(120)],
        "suppressed": [_candidate(f"cut-{index}", shelf="corpus", status="suppressed", tokens=1) for index in range(120)],
    }

    report = build_global_allocator_shadow(trace, candidate_budget=8, max_operation_count=40)

    assert report["operation_count"] == 40
    assert report["proposed_selected_count"] <= 8


def test_query_inspect_includes_shadow_allocator_without_recall_tool_surface(tmp_path: Path) -> None:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "allocator-session",
        platform="test",
        user_id="allocator-user",
        chat_id="allocator-chat",
        thread_id="allocator-thread",
    )
    try:
        assert provider._store is not None
        provider._store.upsert_profile_item(
            stable_key="preference:allocator",
            category="preference",
            content="Allocator trace should be inspect-only.",
            source="allocator.fixture",
            confidence=0.99,
            metadata=provider._scoped_metadata(),
        )

        inspect = json.loads(provider.handle_tool_call("brainstack_inspect", {"query": "allocator inspect-only"}))
        recall = json.loads(provider.handle_tool_call("brainstack_recall", {"query": "allocator inspect-only"}))

        allocator = inspect["report"]["global_allocator_shadow"]
        assert allocator["schema"] == "brainstack.global_allocator_shadow.v1"
        assert allocator["mode"] == "shadow_read_only"
        assert allocator["authority_floor_verdict"] in {"pass", "over_budget_due_to_authority_floor"}
        assert "global_allocator_shadow" not in recall
    finally:
        provider.shutdown()


def test_global_allocator_real_world_like_noise_stays_shadow_only(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        for index in range(10):
            store.add_continuity_event(
                session_id=f"allocator-prior-{index}",
                turn_number=index,
                kind="note",
                content=f"Allocator noise {index} repeats the same token budget story.",
                source="allocator.fixture",
                metadata={"principal_scope_key": PRINCIPAL_SCOPE},
            )
        store.upsert_graph_state(
            subject_name="Allocator Kernel",
            attribute="truth",
            value_text="authority evidence must not be dropped for token savings",
            source="allocator.fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        report = build_query_inspect(
            store,
            query="Allocator token budget authority evidence",
            session_id="allocator-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            continuity_match_limit=6,
            graph_limit=2,
            evidence_item_budget=3,
        )

        allocator = report["global_allocator_shadow"]
        assert allocator["mode"] == "shadow_read_only"
        assert allocator["operation_count"] >= allocator["proposed_selected_count"]
        assert report["final_packet"]["char_count"] > 0
    finally:
        store.close()
