from __future__ import annotations

from brainstack.retrieval_channel_deadlines import build_channel_deadline_statuses


class _Store:
    _corpus_backend = None
    _graph_backend = None


class _ExternalBackend:
    def close(self) -> None:
        return None


def _plan(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "plan_id": "rcp:test",
        "semantic_enabled": True,
        "semantic_allowed_shelves": ["corpus"],
        "shelf_limits": {
            "profile": 0,
            "continuity_match": 0,
            "continuity_recent": 0,
            "transcript": 0,
            "operating": 0,
            "graph": 0,
            "corpus": 4,
            "semantic_evidence": 16,
        },
        "channel_deadlines_ms": {
            "profile": 250,
            "operating": 300,
            "semantic": 1200,
            "graph": 1200,
            "corpus": 1200,
            "temporal": 1200,
        },
    }
    payload.update(overrides)
    return payload


def test_sqlite_semantic_deadline_contract_is_bounded_sync() -> None:
    statuses = build_channel_deadline_statuses(_Store(), retrieval_control_plan=_plan())

    assert statuses["semantic"]["support_status"] == "bounded_sync"
    assert statuses["semantic"]["enforcement"] == "query_limit_bounded_same_thread"
    assert statuses["graph"]["support_status"] == "skipped_by_plan"


def test_external_corpus_semantic_reports_unsupported_cancellation() -> None:
    store = _Store()
    store._corpus_backend = _ExternalBackend()

    statuses = build_channel_deadline_statuses(store, retrieval_control_plan=_plan())

    assert statuses["semantic"]["support_status"] == "cancellation_unsupported"
    assert statuses["semantic"]["enforcement"] == "explicit_unsupported_status"
    assert statuses["semantic"]["hidden_work_after_return"] is None


def test_external_graph_reports_unsupported_only_when_graph_route_allowed() -> None:
    store = _Store()
    store._graph_backend = _ExternalBackend()

    statuses = build_channel_deadline_statuses(
        store,
        retrieval_control_plan=_plan(
            semantic_allowed_shelves=["graph"],
            shelf_limits={
                "profile": 0,
                "continuity_match": 0,
                "continuity_recent": 0,
                "transcript": 0,
                "operating": 0,
                "graph": 4,
                "corpus": 0,
                "semantic_evidence": 16,
            },
        ),
    )

    assert statuses["graph"]["support_status"] == "cancellation_unsupported"
    assert statuses["graph_recall"]["support_status"] == "cancellation_unsupported"
