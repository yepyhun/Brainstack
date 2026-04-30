from __future__ import annotations

from brainstack.mempalace_budget_projection import project_canonical_events_to_mempalace_budget


def _event(
    *,
    event_id: str,
    memory_kind: str,
    budget_class: str,
    truth_eligible: bool,
    support_visibility: str,
    authority_critical: bool = False,
) -> dict:
    return {
        "event": {
            "event_id": event_id,
            "schema_version": "brainstack.canonical_memory_event.v1",
            "event_type": "durable_fact_committed" if truth_eligible else "support_event",
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
            "memory_kind": memory_kind,
            "target_slot": f"{memory_kind}.slot",
            "subject_ref": "entity:subject",
            "predicate": "related_to",
            "object_ref": "entity:object",
            "normalized_value_hash": f"sha256:value_{event_id}",
            "stable_fact_id": f"{memory_kind}:{event_id}",
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
            "valid_to": "",
            "transaction_time": "2026-04-30T10:00:01Z",
            "supersedes": [],
            "superseded_by": "",
        },
        "projection": {
            "entity_refs": [],
            "relation_refs": [],
            "budget_class": budget_class,
            "authority_critical": authority_critical,
            "projection_hints": {
                "graph_ready": memory_kind == "graph_relation",
                "budget_ready": True,
                "multihop_ready": memory_kind == "graph_relation",
            },
        },
        "trace": {
            "proposal_id": f"proposal_{event_id}",
            "donor_trace": {"donor": "hindsight", "donor_version": "test"},
            "policy_versions": {"admission": "test", "slot_registry": "test"},
        },
        "extensions": {},
    }


def test_mempalace_budget_preserves_authority_critical_under_pressure() -> None:
    events = [
        _event(
            event_id="truth",
            memory_kind="profile",
            budget_class="always_active",
            truth_eligible=True,
            support_visibility="answer_evidence",
            authority_critical=True,
        ),
        *[
            _event(
                event_id=f"support_{index}",
                memory_kind="support_only",
                budget_class="support_only",
                truth_eligible=False,
                support_visibility="normal",
            )
            for index in range(8)
        ],
    ]

    projection = project_canonical_events_to_mempalace_budget(events, max_active_tokens=18)

    assert projection["status"] == "pass"
    assert [card["stable_fact_id"] for card in projection["active_cards"]] == ["profile:truth"]
    assert projection["support_only"]
    assert projection["estimated_delta_tokens"] > 0
    assert projection["critical_counters"]["authority_critical_dropped"] == 0


def test_mempalace_budget_fails_closed_without_dropping_authority_truth() -> None:
    events = [
        _event(
            event_id=f"truth_{index}",
            memory_kind="project",
            budget_class="active_if_task_relevant",
            truth_eligible=True,
            support_visibility="answer_evidence",
            authority_critical=True,
        )
        for index in range(3)
    ]

    projection = project_canonical_events_to_mempalace_budget(events, max_active_tokens=10)

    assert projection["status"] == "pass"
    assert projection["fail_closed"] is True
    assert len(projection["active_cards"]) == 3
    assert projection["selected_active_tokens"] > projection["max_active_tokens"]
    assert projection["critical_counters"]["authority_critical_dropped"] == 0


def test_mempalace_budget_keeps_memory_kind_in_every_decision() -> None:
    projection = project_canonical_events_to_mempalace_budget(
        [
            _event(
                event_id="reference",
                memory_kind="reference",
                budget_class="retrieval_only",
                truth_eligible=True,
                support_visibility="inspect_only",
            )
        ]
    )

    assert projection["status"] == "pass"
    assert projection["budget_decisions"][0]["memory_kind"] == "reference"
    assert projection["budget_decisions"][0]["reason_code"] == "DROP_RETRIEVAL_ONLY"


def test_mempalace_budget_does_not_emit_raw_extension_text() -> None:
    event = _event(
        event_id="support_raw",
        memory_kind="support_only",
        budget_class="support_only",
        truth_eligible=False,
        support_visibility="normal",
    )
    event["extensions"] = {"debug.v1": {"raw_text": "private source text"}}

    projection = project_canonical_events_to_mempalace_budget([event])

    assert projection["status"] == "pass"
    assert "private source text" not in str(projection)
    assert projection["critical_counters"]["raw_text_in_budget_projection"] == 0
