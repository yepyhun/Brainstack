from __future__ import annotations

from copy import deepcopy

from brainstack.core.reason_codes import ReasonCode
from brainstack.projection_semantics import classify_projection_semantics


def _event(
    *,
    event_id: str = "cme_projection_1",
    event_type: str = "durable_fact_committed",
    truth_eligible: bool = True,
    support_visibility: str = "answer_evidence",
    receipt_id: str = "1",
    valid_to: str = "",
    superseded_by: str = "",
    budget_class: str = "task_relevant",
    authority_critical: bool = True,
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
            "target_slot": "project.created_by",
            "subject_ref": "entity:project:brainstack",
            "predicate": "created_by",
            "object_ref": "entity:user:creator",
            "normalized_value_hash": f"sha256:value_{event_id}",
            "stable_fact_id": f"stable:{event_id}",
        },
        "authority": {
            "authority_class": "user_explicit",
            "truth_eligible": truth_eligible,
            "support_visibility": support_visibility,
            "confidence": 0.99,
            "admission_decision_id": f"adm_{event_id}",
            "receipt_id": receipt_id,
        },
        "temporal": {
            "valid_from": "2026-04-30T10:00:00Z",
            "valid_to": valid_to,
            "transaction_time": "2026-04-30T10:00:01Z",
            "supersedes": [],
            "superseded_by": superseded_by,
        },
        "projection": {
            "entity_refs": ["entity:project:brainstack", "entity:user:creator"],
            "relation_refs": [f"rel:{event_id}"],
            "budget_class": budget_class,
            "authority_critical": authority_critical,
            "projection_hints": {"graph_ready": True, "budget_ready": True, "multihop_ready": True},
        },
        "trace": {
            "proposal_id": f"proposal_{event_id}",
            "donor_trace": {"donor": "hindsight", "donor_version": "test"},
            "policy_versions": {"admission": "test", "slot_registry": "test"},
        },
        "extensions": {},
    }


def _reason_values(event: dict) -> set[str]:
    return {reason.value for reason in classify_projection_semantics(event).reason_codes}


def test_projection_semantics_marks_current_source_backed_answer_evidence_safe() -> None:
    decision = classify_projection_semantics(_event())

    assert decision.is_current is True
    assert decision.is_prior is False
    assert decision.is_conflicted is False
    assert decision.is_support_only is False
    assert decision.is_answer_safe is True
    assert decision.is_authority_critical is True
    assert ReasonCode.PROJECTION_ANSWER_SAFE_CURRENT_SOURCE_BACKED in decision.reason_codes
    assert ReasonCode.PROJECTION_AUTHORITY_CRITICAL_CANNOT_DROP in decision.reason_codes


def test_projection_semantics_blocks_support_only_history_and_inspect_visibility() -> None:
    for support_visibility in ("normal", "history_only", "inspect_only"):
        decision = classify_projection_semantics(
            _event(
                event_id=f"support_{support_visibility}",
                event_type="support_event",
                truth_eligible=False,
                support_visibility=support_visibility,
                receipt_id="",
                authority_critical=False,
            )
        )

        assert decision.is_support_only is True
        assert decision.is_answer_safe is False
        assert ReasonCode.PROJECTION_SUPPORT_ONLY in decision.reason_codes
        assert ReasonCode.PROJECTION_NOT_ANSWERABLE_SUPPORT_ONLY in decision.reason_codes


def test_projection_semantics_blocks_conflict_and_contradiction_only() -> None:
    conflict = classify_projection_semantics(
        _event(
            event_id="conflict",
            event_type="conflict_opened",
            truth_eligible=False,
            support_visibility="contradiction_only",
            receipt_id="",
            authority_critical=False,
        )
    )

    assert conflict.is_conflicted is True
    assert conflict.is_answer_safe is False
    assert ReasonCode.PROJECTION_CONFLICTED in conflict.reason_codes
    assert ReasonCode.PROJECTION_CONTRADICTION_ONLY in conflict.reason_codes
    assert ReasonCode.PROJECTION_NOT_ANSWERABLE_CONFLICTED in conflict.reason_codes


def test_projection_semantics_blocks_missing_source_refs() -> None:
    event = _event()
    event["source"]["source_span_id"] = ""

    decision = classify_projection_semantics(event)

    assert decision.is_answer_safe is False
    assert ReasonCode.PROJECTION_MISSING_SOURCE_REF in decision.reason_codes
    assert ReasonCode.PROJECTION_NOT_ANSWERABLE_MISSING_SOURCE in decision.reason_codes


def test_projection_semantics_blocks_missing_receipt_for_answer_truth() -> None:
    event = _event(receipt_id="")

    decision = classify_projection_semantics(event)

    assert decision.is_answer_safe is False
    assert ReasonCode.PROJECTION_MISSING_RECEIPT_REF in decision.reason_codes
    assert ReasonCode.PROJECTION_NOT_ANSWERABLE_MISSING_RECEIPT in decision.reason_codes


def test_projection_semantics_marks_expired_and_superseded_prior() -> None:
    expired = classify_projection_semantics(_event(event_id="expired", valid_to="2026-04-30T12:00:00Z"))
    superseded = classify_projection_semantics(_event(event_id="superseded", superseded_by="cme_new"))

    assert expired.is_prior is True
    assert expired.is_current is False
    assert expired.is_answer_safe is False
    assert ReasonCode.PROJECTION_PRIOR_EXPIRED in expired.reason_codes
    assert ReasonCode.PROJECTION_NOT_ANSWERABLE_PRIOR in expired.reason_codes
    assert superseded.is_prior is True
    assert ReasonCode.PROJECTION_PRIOR_SUPERSEDED in superseded.reason_codes


def test_projection_semantics_keeps_authority_critical_orthogonal_to_answer_safety() -> None:
    decision = classify_projection_semantics(
        _event(
            event_id="authority_support",
            event_type="support_event",
            truth_eligible=False,
            support_visibility="normal",
            receipt_id="",
            authority_critical=True,
        )
    )

    assert decision.is_authority_critical is True
    assert decision.is_answer_safe is False
    assert ReasonCode.PROJECTION_AUTHORITY_CRITICAL_KEEP in decision.reason_codes
    assert ReasonCode.PROJECTION_AUTHORITY_CRITICAL_CANNOT_DROP in decision.reason_codes
    assert ReasonCode.PROJECTION_NOT_ANSWERABLE_SUPPORT_ONLY in decision.reason_codes


def test_projection_semantics_marks_retrieval_only_without_answer_upgrade() -> None:
    decision = classify_projection_semantics(
        _event(
            event_id="retrieval",
            support_visibility="inspect_only",
            truth_eligible=True,
            budget_class="retrieval_only",
            authority_critical=False,
        )
    )

    assert decision.is_retrieval_only is True
    assert decision.is_answer_safe is False
    assert ReasonCode.PROJECTION_RETRIEVAL_ONLY in decision.reason_codes
    assert ReasonCode.PROJECTION_NOT_ANSWERABLE_SUPPORT_ONLY in decision.reason_codes


def test_projection_semantics_honors_explicit_hidden_policy_flag() -> None:
    event = _event()
    event["projection"]["hidden"] = True

    decision = classify_projection_semantics(event)

    assert decision.is_hidden is True
    assert decision.is_answer_safe is False
    assert ReasonCode.PROJECTION_HIDDEN_BY_POLICY in decision.reason_codes
    assert ReasonCode.PROJECTION_NOT_ANSWERABLE_HIDDEN in decision.reason_codes


def test_projection_semantics_does_not_mutate_input() -> None:
    event = _event()
    before = deepcopy(event)

    classify_projection_semantics(event)

    assert event == before


def test_projection_semantics_public_output_excludes_raw_private_text() -> None:
    event = _event()
    event["extensions"] = {"debug.v1": {"raw_text": "private source text", "raw_private_text": "secret"}}

    public = classify_projection_semantics(event).to_public_dict()

    assert "private source text" not in str(public)
    assert "secret" not in str(public)
    assert public["event_id"] == "cme_projection_1"
    assert public["reason_codes"]


def test_projection_semantics_reason_codes_are_registered_public_values() -> None:
    event = _event(valid_to="2026-04-30T12:00:00Z")

    for reason in _reason_values(event):
        assert reason in {item.value for item in ReasonCode}
