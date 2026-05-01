from __future__ import annotations

from brainstack.projection_inspect import build_projection_doctor_section, build_projection_inspect_report


def _event(
    *,
    event_id: str,
    event_type: str = "durable_fact_committed",
    truth_eligible: bool = True,
    support_visibility: str = "answer_evidence",
    receipt_id: str = "1",
    valid_to: str = "",
    budget_class: str = "task_relevant",
    authority_critical: bool = True,
    hidden: bool = False,
    source_span_id: str | None = None,
    raw_extension: bool = False,
) -> dict:
    source_span = f"span_{event_id}" if source_span_id is None else source_span_id
    event = {
        "event": {
            "event_id": event_id,
            "schema_version": "brainstack.canonical_memory_event.v1",
            "event_type": event_type,
            "idempotency_key": f"sha256:{event_id}",
        },
        "source": {
            "source_event_id": f"evt_{event_id}",
            "source_span_id": source_span,
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
            "subject_ref": f"entity:subject:{event_id}",
            "predicate": "created_by",
            "object_ref": f"entity:object:{event_id}",
            "normalized_value_hash": f"sha256:value_{event_id}",
            "stable_fact_id": f"stable:{event_id}",
        },
        "authority": {
            "authority_class": "user_explicit" if truth_eligible else "support_only",
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
            "superseded_by": "",
        },
        "projection": {
            "entity_refs": [f"entity:subject:{event_id}", f"entity:object:{event_id}"],
            "relation_refs": [f"rel:{event_id}"],
            "budget_class": budget_class,
            "authority_critical": authority_critical,
            "hidden": hidden,
            "projection_hints": {"graph_ready": True, "budget_ready": True, "multihop_ready": True},
        },
        "trace": {
            "proposal_id": f"proposal_{event_id}",
            "donor_trace": {"donor": "hindsight", "donor_version": "test"},
            "policy_versions": {"admission": "test", "slot_registry": "test"},
        },
        "extensions": {},
    }
    if raw_extension:
        event["extensions"] = {"debug.v1": {"raw_text": "private source text", "raw_private_text": "secret"}}
    return event


def _by_event(report: dict) -> dict[str, dict]:
    return {item["event_id"]: item for item in report["event_explanations"]}


def test_projection_inspect_explains_included_and_excluded_decisions() -> None:
    report = build_projection_inspect_report(
        [
            _event(event_id="truth"),
            _event(
                event_id="support",
                event_type="support_event",
                truth_eligible=False,
                support_visibility="normal",
                receipt_id="",
                authority_critical=False,
            ),
            _event(
                event_id="conflict",
                event_type="conflict_opened",
                truth_eligible=False,
                support_visibility="contradiction_only",
                receipt_id="",
                authority_critical=False,
            ),
            _event(event_id="prior", valid_to="2026-04-30T12:00:00Z"),
            _event(
                event_id="retrieval",
                support_visibility="inspect_only",
                budget_class="retrieval_only",
                authority_critical=False,
            ),
            _event(event_id="hidden", hidden=True),
        ]
    )
    by_event = _by_event(report)

    assert report["verdict"] == "pass"
    assert by_event["truth"]["answer_decision"] == "answer_safe"
    assert by_event["truth"]["surface_actions"] == {
        "graph": "answerable_current_edge",
        "budget": "active",
        "multihop": "traversable",
        "packet": "selected",
    }
    assert "support-only" in by_event["support"]["labels"]
    assert by_event["support"]["surface_actions"]["packet"] == "dropped"
    assert "conflicted" in by_event["conflict"]["labels"]
    assert by_event["conflict"]["surface_actions"]["multihop"] == "blocked"
    assert "prior" in by_event["prior"]["labels"]
    assert by_event["prior"]["surface_actions"]["packet"] == "dropped"
    assert "retrieval-only" in by_event["retrieval"]["labels"]
    assert by_event["retrieval"]["surface_actions"]["budget"] == "retrieval_only"
    assert "hidden" in by_event["hidden"]["labels"]
    assert by_event["hidden"]["answer_decision"] == "not_answer_safe"


def test_projection_inspect_explains_authority_critical_without_answer_upgrade() -> None:
    report = build_projection_inspect_report(
        [
            _event(
                event_id="critical_support",
                event_type="support_event",
                truth_eligible=False,
                support_visibility="normal",
                receipt_id="",
                authority_critical=True,
            )
        ]
    )
    item = report["event_explanations"][0]

    assert report["verdict"] == "pass"
    assert "authority-critical" in item["labels"]
    assert item["answer_decision"] == "not_answer_safe"
    assert "projection_authority_critical_cannot_drop" in item["reason_codes"]
    assert "does not upgrade answer safety" in item["explanation"]


def test_projection_inspect_reports_missing_source_as_doctor_attention() -> None:
    report = build_projection_inspect_report([_event(event_id="missing_source", source_span_id="")])
    doctor = build_projection_doctor_section(
        {
            "status": report["conformance_status"],
            "surface_status": report["surface_status"],
            "critical_counters": report["critical_counters"],
            "event_semantics": [],
            "issues": report["issues"],
        }
    )

    assert report["verdict"] == "needs_attention"
    assert report["issues"]
    assert doctor["status"] == "degraded"
    assert doctor["issue_count"] > 0


def test_projection_inspect_output_is_public_safe() -> None:
    report = build_projection_inspect_report([_event(event_id="raw_extension", raw_extension=True)])

    assert report["verdict"] == "pass"
    assert "private source text" not in str(report)
    assert "secret" not in str(report)
    assert not any(issue["code"] == "raw_text_in_projection_inspect" for issue in report["issues"])
