from __future__ import annotations

from pathlib import Path

from brainstack.control_plane import build_working_memory_packet
from brainstack.db import BrainstackStore
from brainstack.current_truth_view import rebuild_current_truth_view
from scripts.verify_current_truth_l0_snapshot import build_report
from tests.test_current_truth_view import FIXED_REBUILT_AT, _event


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def test_canonical_event_write_updates_l0_snapshot_and_matches_rebuild(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        events = [
            _event(event_id="safe_current"),
            _event(event_id="expired_prior", valid_to="2026-05-03T11:59:30Z"),
            _event(event_id="support_only", event_type="support_event", truth_eligible=False, support_visibility="inspect_only", receipt_id=""),
        ]
        for event in events:
            store.record_canonical_memory_event(event)

        store.rebuild_current_truth_l0_snapshot(projected_at=FIXED_REBUILT_AT)
        snapshot = store.get_current_truth_l0_snapshot(checked_at=FIXED_REBUILT_AT)
        rebuilt = rebuild_current_truth_view(events, rebuilt_at=FIXED_REBUILT_AT, checked_at=FIXED_REBUILT_AT)

        assert snapshot["contract"]["second_write_authority"] is False
        assert snapshot["contract"]["l0_snapshot_is_projection_only"] is True
        assert snapshot["rebuild"]["source"] == "current_truth_l0_snapshot"
        assert snapshot["rebuild"]["ordinary_hot_path_rebuild"] is False
        assert snapshot["current_truth_rows"] == rebuilt["current_truth_rows"]
        assert snapshot["non_answerable_rows"] == rebuilt["non_answerable_rows"]
        assert snapshot["counters"] == rebuilt["counters"]
    finally:
        store.close()


def test_working_memory_packet_uses_l0_snapshot_without_canonical_event_rebuild(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.record_canonical_memory_event(_event(event_id="safe_current"))

        def forbidden_list_canonical_memory_events(**_kwargs: object) -> list[dict]:
            raise AssertionError("hot path must read current_truth_l0_rows, not rebuild canonical events")

        store.list_canonical_memory_events = forbidden_list_canonical_memory_events  # type: ignore[method-assign]
        packet = build_working_memory_packet(
            store,
            query="structured current truth request",
            session_id="session:test",
            principal_scope_key="principal:a",
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
            adaptive_route_signals={"required_evidence_classes": ["current_truth"]},
        )

        assert packet["current_truth_view"]["rebuild"]["source"] == "current_truth_l0_snapshot"
        assert packet["current_truth_view"]["rebuild"]["ordinary_hot_path_rebuild"] is False
        assert packet["adaptive_route_plan"]["route_class"] == "current_truth"
    finally:
        store.close()


def test_current_truth_route_uses_targeted_l0_when_slot_hint_exists(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.record_canonical_memory_event(_event(event_id="safe_current"))
        calls = {"targeted": 0}
        original_targeted = store.get_current_truth_l0_candidates

        def spy_get_current_truth_l0_candidates(**kwargs: object) -> dict:
            calls["targeted"] += 1
            assert kwargs["target_slots"] == ("profile.preferred_language",)
            return original_targeted(**kwargs)

        def forbidden_get_current_truth_l0_snapshot(**_kwargs: object) -> dict:
            raise AssertionError("targeted current-truth route must not read a broad L0 snapshot")

        def forbidden_list_canonical_memory_events(**_kwargs: object) -> list[dict]:
            raise AssertionError("hot path must not rebuild current truth from canonical events")

        store.get_current_truth_l0_candidates = spy_get_current_truth_l0_candidates  # type: ignore[method-assign]
        store.get_current_truth_l0_snapshot = forbidden_get_current_truth_l0_snapshot  # type: ignore[method-assign]
        store.list_canonical_memory_events = forbidden_list_canonical_memory_events  # type: ignore[method-assign]

        packet = build_working_memory_packet(
            store,
            query="structured current truth request",
            session_id="session:test",
            principal_scope_key="principal:a",
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
            adaptive_route_signals={
                "required_evidence_classes": ["current_truth"],
                "current_truth_target_slots": ["profile.preferred_language"],
            },
        )

        assert calls["targeted"] == 1
        assert packet["current_truth_view"]["rebuild"]["source"] == "current_truth_l0_targeted"
        assert packet["adaptive_route_plan"]["route_class"] == "current_truth"
    finally:
        store.close()


def test_current_truth_l0_verifier_passes() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["parity"]["status"] == "pass"
    assert report["summary"]["ordinary_hot_path_rebuild"] is False
