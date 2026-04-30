from __future__ import annotations

from brainstack.multihop_readiness import build_multihop_readiness_projection


def _event(
    *,
    event_id: str,
    subject_ref: str,
    predicate: str,
    object_ref: str,
    event_type: str = "durable_fact_committed",
    truth_eligible: bool = True,
    support_visibility: str = "answer_evidence",
    valid_to: str = "",
) -> dict:
    return {
        "event": {
            "event_id": event_id,
            "schema_version": "brainstack.canonical_memory_event.v1",
            "event_type": event_type,
            "idempotency_key": f"sha256:{event_id}",
        },
        "source": {
            "source_event_id": f"evt_{event_id}",
            "source_span_id": f"span_{event_id}",
            "source_quote_hash": f"sha256:quote_{event_id}",
            "speaker": "user",
            "assertion_speaker": "user",
            "source_modality": "conversation",
            "observed_at": "2026-04-30T10:00:00Z",
        },
        "scope": {
            "tenant_id": "local",
            "principal_scope_key": "principal:a",
            "workspace_scope_key": "workspace:a",
            "session_id": "session:a",
        },
        "claim": {
            "memory_kind": "graph_relation",
            "target_slot": predicate,
            "subject_ref": subject_ref,
            "predicate": predicate,
            "object_ref": object_ref,
            "normalized_value_hash": f"sha256:value_{event_id}",
            "stable_fact_id": f"{subject_ref}:{predicate}:{object_ref}",
        },
        "authority": {
            "authority_class": "user_explicit" if truth_eligible else "support_only",
            "truth_eligible": truth_eligible,
            "support_visibility": support_visibility,
            "confidence": 0.95,
            "admission_decision_id": f"adm_{event_id}",
            "receipt_id": "1" if truth_eligible else "",
        },
        "temporal": {
            "valid_from": "2026-04-30T10:00:00Z",
            "valid_to": valid_to,
            "transaction_time": "2026-04-30T10:00:01Z",
            "supersedes": [],
            "superseded_by": "",
        },
        "projection": {
            "entity_refs": [subject_ref, object_ref],
            "relation_refs": [f"rel:{event_id}"],
            "budget_class": "task_relevant",
            "authority_critical": truth_eligible,
            "projection_hints": {"graph_ready": True, "budget_ready": True, "multihop_ready": True},
        },
        "trace": {
            "proposal_id": f"proposal_{event_id}",
            "donor_trace": {"donor": "hindsight", "donor_version": "test"},
            "policy_versions": {"admission": "test", "slot_registry": "test"},
        },
        "extensions": {},
    }


def test_multihop_readiness_preserves_two_hop_path_metadata() -> None:
    projection = build_multihop_readiness_projection(
        [
            _event(event_id="edge_a_b", subject_ref="entity:a", predicate="depends_on", object_ref="entity:b"),
            _event(event_id="edge_b_c", subject_ref="entity:b", predicate="uses", object_ref="entity:c"),
        ]
    )

    assert projection["status"] == "pass"
    assert len(projection["traversal_edges"]) == 2
    for edge in projection["traversal_edges"]:
        assert edge["traversal_allowed"] is True
        assert edge["direction"] == "subject_to_object"
        assert edge["source_event_id"]
        assert edge["source_span_id"]
        assert edge["source_quote_hash"]
        assert edge["retrieval_trace"]["path_trace_id"].startswith("sha256:")


def test_multihop_readiness_blocks_support_only_edge() -> None:
    projection = build_multihop_readiness_projection(
        [
            _event(
                event_id="support_edge",
                subject_ref="entity:a",
                predicate="maybe_related_to",
                object_ref="entity:b",
                event_type="support_event",
                truth_eligible=False,
                support_visibility="normal",
            )
        ]
    )

    assert projection["status"] == "pass"
    assert projection["traversal_edges"] == []
    assert len(projection["blocked_edges"]) == 1
    assert projection["blocked_edges"][0]["traversal_allowed"] is False
    assert projection["blocked_edges"][0]["reason_code"] == "BLOCKED_NOT_ANSWER_EVIDENCE"


def test_multihop_readiness_blocks_expired_edge() -> None:
    projection = build_multihop_readiness_projection(
        [
            _event(
                event_id="expired_edge",
                subject_ref="entity:a",
                predicate="owned_by",
                object_ref="entity:b",
                valid_to="2026-04-30T12:00:00Z",
            )
        ]
    )

    assert projection["status"] == "pass"
    assert projection["traversal_edges"] == []
    assert len(projection["blocked_edges"]) == 1
    assert projection["blocked_edges"][0]["traversal_allowed"] is False


def test_multihop_readiness_blocks_conflicted_edge() -> None:
    projection = build_multihop_readiness_projection(
        [
            _event(
                event_id="conflict_edge",
                subject_ref="entity:a",
                predicate="created_by",
                object_ref="entity:b",
                event_type="conflict_opened",
                truth_eligible=False,
                support_visibility="contradiction_only",
            )
        ]
    )

    assert projection["status"] == "pass"
    assert projection["traversal_edges"] == []
    assert projection["blocked_edges"][0]["reason_code"] == "BLOCKED_CONFLICT_OR_CONTRADICTION"
