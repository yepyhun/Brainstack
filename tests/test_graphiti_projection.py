from __future__ import annotations

from copy import deepcopy

from brainstack.graphiti_projection import project_canonical_events_to_graphiti


def _event(
    *,
    event_id: str = "cme_graph_1",
    memory_kind: str = "graph_relation",
    event_type: str = "durable_fact_committed",
    truth_eligible: bool = True,
    support_visibility: str = "answer_evidence",
    receipt_id: str = "1",
    valid_to: str = "",
    principal_scope_key: str = "principal:a",
) -> dict:
    return {
        "event": {
            "event_id": event_id,
            "schema_version": "brainstack.canonical_memory_event.v1",
            "event_type": event_type,
            "idempotency_key": f"sha256:{event_id}",
        },
        "source": {
            "source_event_id": "evt_1",
            "source_span_id": "span_1",
            "source_quote_hash": "sha256:quote",
            "speaker": "user",
            "assertion_speaker": "user",
            "source_modality": "conversation",
            "observed_at": "2026-04-30T10:00:00Z",
        },
        "scope": {
            "tenant_id": "local",
            "principal_scope_key": principal_scope_key,
            "workspace_scope_key": "workspace:a",
            "session_id": "session:a",
        },
        "claim": {
            "memory_kind": memory_kind,
            "target_slot": "project.created_by",
            "subject_ref": "entity:project:brainstack",
            "predicate": "created_by",
            "object_ref": "entity:user:creator",
            "normalized_value_hash": "sha256:value",
            "stable_fact_id": "project:brainstack:created_by",
        },
        "authority": {
            "authority_class": "user_explicit",
            "truth_eligible": truth_eligible,
            "support_visibility": support_visibility,
            "confidence": 0.99,
            "admission_decision_id": "adm_1",
            "receipt_id": receipt_id,
        },
        "temporal": {
            "valid_from": "2026-04-30T10:00:00Z",
            "valid_to": valid_to,
            "transaction_time": "2026-04-30T10:00:01Z",
            "supersedes": [],
            "superseded_by": "",
        },
        "projection": {
            "entity_refs": ["entity:project:brainstack", "entity:user:creator"],
            "relation_refs": ["rel:brainstack:created_by:creator"],
            "budget_class": "task_relevant",
            "authority_critical": True,
            "projection_hints": {
                "graph_ready": memory_kind == "graph_relation",
                "budget_ready": True,
                "multihop_ready": memory_kind == "graph_relation",
            },
        },
        "trace": {
            "proposal_id": "proposal_1",
            "donor_trace": {"donor": "hindsight", "donor_version": "test"},
            "policy_versions": {"admission": "test", "slot_registry": "test"},
        },
        "extensions": {},
    }


def test_graphiti_projection_projects_answerable_current_edge() -> None:
    projection = project_canonical_events_to_graphiti([_event()])

    assert projection["status"] == "pass"
    assert projection["critical_counters"]["non_graph_memory_kind_projected"] == 0
    assert len(projection["episodes"]) == 1
    assert len(projection["entities"]) == 2
    assert len(projection["current_edges"]) == 1
    edge = projection["current_edges"][0]
    assert edge["answerable"] is True
    assert "projection_answer_safe_current_source_backed" in edge["projection_reason_codes"]
    assert edge["projection_semantics"]["is_answer_safe"] is True
    assert edge["source_event_id"] == "evt_1"
    assert edge["source_span_id"] == "span_1"
    assert edge["valid_to"] == ""
    assert edge["scope"]["principal_scope_key"] == "principal:a"


def test_graphiti_projection_excludes_non_graph_memory_kind_from_graph_truth() -> None:
    event = _event(memory_kind="preference")
    event["projection"]["projection_hints"]["graph_ready"] = False

    projection = project_canonical_events_to_graphiti([event])

    assert projection["status"] == "pass"
    assert projection["current_edges"] == []
    assert projection["inspect_only_edges"] == []
    assert projection["skipped"][0]["reason"] == "NON_GRAPH_MEMORY_KIND"


def test_graphiti_projection_keeps_support_only_graph_relation_inspect_only() -> None:
    projection = project_canonical_events_to_graphiti(
        [_event(truth_eligible=False, support_visibility="inspect_only", event_type="proposal_rejected")]
    )

    assert projection["status"] == "pass"
    assert projection["current_edges"] == []
    assert len(projection["inspect_only_edges"]) == 1
    edge = projection["inspect_only_edges"][0]
    assert edge["answerable"] is False
    assert "projection_support_only" in edge["projection_reason_codes"]
    assert edge["projection_semantics"]["is_support_only"] is True


def test_graphiti_projection_keeps_expired_relation_prior_not_current() -> None:
    projection = project_canonical_events_to_graphiti(
        [_event(valid_to="2026-04-30T12:00:00Z")]
    )

    assert projection["status"] == "pass"
    assert projection["current_edges"] == []
    assert len(projection["prior_edges"]) == 1
    edge = projection["prior_edges"][0]
    assert edge["answerable"] is False
    assert edge["current"] is False
    assert "projection_prior_expired" in edge["projection_reason_codes"]


def test_graphiti_projection_keeps_conflict_non_answerable() -> None:
    event = _event(
        event_id="cme_conflict_1",
        event_type="conflict_opened",
        truth_eligible=False,
        support_visibility="contradiction_only",
    )

    projection = project_canonical_events_to_graphiti([event])

    assert projection["status"] == "pass"
    assert projection["current_edges"] == []
    assert len(projection["inspect_only_edges"]) == 1
    edge = projection["inspect_only_edges"][0]
    assert edge["conflicted"] is True
    assert edge["answerable"] is False
    assert "projection_contradiction_only" in edge["projection_reason_codes"]
    assert edge["projection_semantics"]["is_conflicted"] is True


def test_graphiti_projection_blocks_missing_receipt_proposal_accepted() -> None:
    event = _event(
        event_id="cme_missing_receipt",
        event_type="proposal_accepted",
        receipt_id="",
    )

    projection = project_canonical_events_to_graphiti([event])

    assert projection["status"] == "pass"
    assert projection["current_edges"] == []
    assert len(projection["inspect_only_edges"]) == 1
    edge = projection["inspect_only_edges"][0]
    assert edge["answerable"] is False
    assert edge["current"] is True
    assert "projection_not_answerable_missing_receipt" in edge["projection_reason_codes"]
    assert edge["projection_semantics"]["is_answer_safe"] is False


def test_graphiti_projection_shared_semantics_are_public_safe() -> None:
    event = _event(event_id="cme_raw_extension")
    event["extensions"] = {"debug.v1": {"raw_text": "private source text"}}

    projection = project_canonical_events_to_graphiti([event])

    edge = projection["current_edges"][0]
    assert "private source text" not in str(edge["projection_semantics"])


def test_graphiti_projection_rebuild_is_deterministic() -> None:
    a = _event(event_id="cme_graph_a", principal_scope_key="principal:a")
    b = _event(event_id="cme_graph_b", principal_scope_key="principal:b")

    projection_1 = project_canonical_events_to_graphiti([b, a])
    projection_2 = project_canonical_events_to_graphiti([deepcopy(a), deepcopy(b)])

    assert projection_1 == projection_2
