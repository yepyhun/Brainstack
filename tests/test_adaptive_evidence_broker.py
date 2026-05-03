from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from brainstack.adaptive_evidence_broker import (
    BROKER_TRACE_SCHEMA,
    CANDIDATE_SCHEMA,
    build_broker_trace,
    build_broker_trace_from_packet,
    normalize_broker_candidate,
    validate_broker_trace,
)
from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.retrieval_pipeline.runtime import EvidenceCandidate

PRIVATE_TEXT = "private-token-should-not-leak-from-broker"


def _safe_candidate(**overrides: Any) -> dict[str, Any]:
    candidate = {
        "candidate_id": "candidate-safe-1",
        "evidence_id": "evidence-safe-1",
        "shelf": "profile",
        "channel": "semantic",
        "authority": "durable_truth",
        "truth_eligible": True,
        "answer_evidence_allowed": True,
        "protected": True,
        "source_role": "user",
        "source_event_id": "turn-public-1",
        "source_span_id": "span-public-1",
        "admission_id": "admission-public-1",
        "receipt_id": "receipt-public-1",
        "decision": "selected",
        "reason_code": "selected_budget_protected_authority",
        "token_estimate": 8,
        "rrf_score": 0.42,
        "keyword_score": 1.0,
        "semantic_score": 0.5,
        "freshness": "current",
        "content": PRIVATE_TEXT,
    }
    candidate.update(overrides)
    return candidate


def test_normalizes_existing_evidence_candidate_without_private_text() -> None:
    source = EvidenceCandidate(
        key="profile:private-key-material",
        shelf="profile",
        row=_safe_candidate(stable_key="profile:private-key-material", content=PRIVATE_TEXT),
        rrf_score=0.75,
        channel_ranks={"semantic": 1, "keyword": 3},
    )

    normalized = normalize_broker_candidate(source, selection_status="selected")

    encoded = json.dumps(normalized, sort_keys=True)
    assert normalized["schema"] == CANDIDATE_SCHEMA
    assert PRIVATE_TEXT not in encoded
    assert "private-key-material" not in encoded
    assert normalized["candidate_id"].startswith("sha256:")
    assert normalized["shelf"] == "profile"
    assert normalized["channels"] == ["keyword", "semantic"]
    assert normalized["authority"]["class"] == "durable_truth"
    assert normalized["authority"]["truth_eligible"] is True
    assert normalized["authority"]["answer_truth_allowed"] is True
    assert normalized["relevance"]["rrf_score"] == 0.75
    assert normalized["freshness"]["class"] == "current"
    assert normalized["cost"]["token_estimate"] == 8
    assert normalized["provenance"]["source_present"] is True
    assert normalized["selection"]["status"] == "selected"
    assert normalized["failure_bundle"]["present"] is False


def test_broker_never_upgrades_unsafe_candidates_to_answer_truth() -> None:
    unsafe_cases = {
        "support_only": _safe_candidate(authority="support_only", truth_eligible=False, answer_evidence_allowed=False),
        "conflict": _safe_candidate(row_type="conflict", support_visibility="contradiction_only"),
        "stale_prior": _safe_candidate(freshness="prior", stale=True),
        "missing_source": _safe_candidate(source_event_id="", source_span_id="", admission_id="", receipt_id=""),
        "assistant_authored": _safe_candidate(source_role="assistant"),
        "fake_receipt": _safe_candidate(admission_id="", source_event_id="", source_span_id="", receipt_id="receipt-only"),
        "malformed": {"content": PRIVATE_TEXT, "decision": "selected"},
    }

    for label, candidate in unsafe_cases.items():
        normalized = normalize_broker_candidate(candidate, selection_status="selected")
        assert normalized["authority"]["answer_truth_allowed"] is False, label
        assert normalized["failure_bundle"]["present"] is True, label
        assert normalized["selection"]["status"] in {"selected", "malformed"}


def test_broker_trace_is_read_only_and_public_safe() -> None:
    candidate = _safe_candidate(content=PRIVATE_TEXT)
    packet = {
        "packet_budget": {
            "budget_decisions": [candidate, _safe_candidate(candidate_id="support-1", authority="support_only", decision="dropped")]
        }
    }
    before = deepcopy(packet)

    trace = build_broker_trace_from_packet(packet)

    assert packet == before
    assert trace["schema"] == BROKER_TRACE_SCHEMA
    assert trace["mode"] == "read_only_projection"
    assert trace["selected_count"] == 1
    assert trace["suppressed_count"] == 1
    assert validate_broker_trace(trace) == []
    assert PRIVATE_TEXT not in json.dumps(trace, sort_keys=True)


def test_broker_trace_reports_selected_and_suppressed_from_existing_candidate_trace() -> None:
    retrieval_trace = {
        "schema": "brainstack.retrieval_candidate_trace.v1",
        "selected": [
            {
                "candidate_id": "selected-public",
                "evidence_key": "profile:visible-key",
                "shelf": "profile",
                "selection": {"status": "selected", "reason": "selected_by_final_packet"},
                "authority": {"level": "canonical", "floor_applied": True},
                "score": {"rrf": 0.7, "keyword": 1.0, "semantic": 0.2},
                "cost": {"preview_token_estimate": 5},
                "source": {"retrieval_source": "profile", "channels": ["keyword"]},
                "donor_metadata": {"brainstack": {"stable_key": "profile:visible-key"}},
            }
        ],
        "suppressed": [
            {
                "candidate_id": "suppressed-public",
                "evidence_key": "continuity:overflow",
                "shelf": "continuity_match",
                "selection": {"status": "suppressed", "reason": "not_selected"},
                "authority": {"level": "support_only"},
                "score": {"rrf": 0.1},
                "cost": {"preview_token_estimate": 12},
            }
        ],
    }

    trace = build_broker_trace(retrieval_trace=retrieval_trace)

    assert trace["selected_count"] == 1
    assert trace["suppressed_count"] == 1
    assert trace["selected"][0]["selection"]["status"] == "selected"
    assert trace["suppressed"][0]["selection"]["drop_reason"] == "not_selected"
    assert validate_broker_trace(trace) == []


def test_query_inspect_exposes_adaptive_broker_without_recall_payload_leak(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        scope = "principal:m007:s02:broker"
        store.upsert_profile_item(
            stable_key="identity:m007:s02",
            category="identity",
            content=f"Public broker fixture {PRIVATE_TEXT}",
            source="broker.fixture",
            confidence=0.99,
            metadata={"principal_scope_key": scope, "truth_eligible": True},
        )

        report = build_query_inspect(
            store,
            query="Public broker fixture",
            session_id="session:m007:s02:broker",
            principal_scope_key=scope,
            profile_match_limit=4,
            continuity_match_limit=2,
            continuity_recent_limit=2,
            transcript_match_limit=0,
            graph_limit=0,
            corpus_limit=0,
            evidence_item_budget=4,
        )

        broker = report["adaptive_evidence_broker"]
        assert broker["schema"] == BROKER_TRACE_SCHEMA
        assert broker["selected_count"] >= 1
        assert validate_broker_trace(broker) == []
        assert PRIVATE_TEXT not in json.dumps(broker, sort_keys=True)
        assert "adaptive_evidence_broker" not in report["final_packet"]["preview"]
    finally:
        store.close()
