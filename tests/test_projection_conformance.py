from __future__ import annotations

from brainstack.projection_conformance import build_projection_conformance_report


def _event(
    *,
    event_id: str,
    event_type: str = "durable_fact_committed",
    truth_eligible: bool = True,
    support_visibility: str = "answer_evidence",
    receipt_id: str = "1",
    valid_to: str = "",
    source_span_id: str | None = None,
    authority_critical: bool = True,
    extension_raw_text: bool = False,
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
            "budget_class": "task_relevant",
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
    if extension_raw_text:
        event["extensions"] = {"debug.v1": {"raw_text": "private source text"}}
    return event


def test_projection_conformance_passes_cross_surface_safety_contract() -> None:
    report = build_projection_conformance_report(
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
            _event(event_id="missing_receipt", event_type="proposal_accepted", receipt_id=""),
        ],
        max_packet_tokens=12,
    )

    assert report["status"] == "pass"
    assert report["critical_counters"]["graph_unsafe_answerable"] == 0
    assert report["critical_counters"]["multihop_unsafe_traversal"] == 0
    assert report["critical_counters"]["budget_unsafe_answer_safe"] == 0
    assert report["critical_counters"]["packet_unsafe_selected"] == 0
    assert report["graph"]["current_edge_ids"] == ["truth"]
    assert report["multihop"]["traversal_event_ids"] == ["truth"]
    assert set(report["packet"]["selected_event_ids"]) == {"truth"}
    assert {"support", "conflict", "prior", "missing_receipt"}.issubset(
        set(report["packet"]["dropped_event_ids"])
    )


def test_projection_conformance_preserves_all_answer_safe_authority_under_packet_pressure() -> None:
    report = build_projection_conformance_report(
        [_event(event_id="truth_a"), _event(event_id="truth_b")],
        max_packet_tokens=10,
    )

    assert report["status"] == "pass"
    assert report["surface_status"]["packet_fail_closed"] is True
    assert set(report["packet"]["selected_event_ids"]) == {"truth_a", "truth_b"}
    assert report["critical_counters"]["packet_authority_critical_dropped"] == 0


def test_projection_conformance_reports_missing_source_visibly_without_answer_truth() -> None:
    report = build_projection_conformance_report(
        [_event(event_id="missing_source", source_span_id="")]
    )

    assert report["status"] == "fail"
    assert report["surface_status"]["graph"] == "fail"
    assert report["critical_counters"]["graph_unsafe_answerable"] == 0
    assert report["critical_counters"]["packet_unsafe_selected"] == 0
    missing = next(item for item in report["event_semantics"] if item["event_id"] == "missing_source")
    assert missing["is_answer_safe"] is False
    assert "projection_not_answerable_missing_source" in missing["reason_codes"]


def test_projection_conformance_report_is_public_safe() -> None:
    report = build_projection_conformance_report(
        [_event(event_id="raw_extension", extension_raw_text=True)]
    )

    assert report["status"] == "pass"
    assert report["critical_counters"]["raw_text_in_report"] == 0
    assert "private source text" not in str(report)
    assert "raw_private_text" not in str(report)
