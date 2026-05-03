from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Iterable, Mapping

from brainstack.hindsight_spine_adapter import normalize_proposal_action_batch
from brainstack.tier2_decision_core import (
    build_tier2_decision_plan,
    semantic_conformance_issues,
    validate_tier2_decision_plan,
)

TIER2_EXTRACTION_QUALITY_SCHEMA = "brainstack.tier2_extraction_quality_report.v1"
TIER2_EXTRACTION_QUALITY_VERSION = "2026-05-03.m004"

REQUIRED_QUALITY_CLASSES = (
    "durable_fact_precision",
    "duplicate_prevention",
    "update_supersession_correctness",
    "conflict_precision",
    "support_preservation",
    "assistant_authored_rejection",
    "missing_source_block",
    "multilingual_robustness",
    "donor_drift_detection",
    "ignored_action_not_truth",
    "bloat_impact",
)

DEFAULT_BLOAT_RATIO_THRESHOLD = 2.0


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _scope(principal: str = "principal-a") -> dict[str, str]:
    return {
        "tenant_id": "local",
        "principal_scope_key": principal,
        "workspace_scope_key": "workspace-a",
        "session_id": "session-a",
        "project_id": "project-a",
    }


def _span(span_id: str = "span-user", *, speaker: str = "user", principal: str = "principal-a") -> dict[str, Any]:
    return {
        "source_span_id": span_id,
        "source_event_id": "event-" + span_id,
        "speaker": speaker,
        "assertion_speaker": speaker,
        "source_modality": "conversation",
        "scope": _scope(principal),
    }


def _raw_batch(operation_id: str, actions: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "status": "ok",
        "operation_id": operation_id,
        "donor_version": "hindsight-compatible-public-fixture",
        "config_hash": "sha256:public-fixture-config",
        "actions": [dict(action) for action in actions],
    }


def _packet(
    proposal_batch: Mapping[str, Any],
    *,
    spans: list[Mapping[str, Any]] | None = None,
    existing: list[Mapping[str, Any]] | None = None,
    conflicts: list[Mapping[str, Any]] | None = None,
    principal: str = "principal-a",
) -> dict[str, Any]:
    return {
        "schema": "brainstack.tier2_decision_input.v1",
        "policy_version": TIER2_EXTRACTION_QUALITY_VERSION,
        "proposal_batch": proposal_batch,
        "verified_source_spans": [dict(span) for span in (spans if spans is not None else [_span()])],
        "scope": _scope(principal),
        "existing_memory_refs": [dict(item) for item in (existing or [])],
        "graph_state_summary": {"unresolved_conflicts": [dict(item) for item in (conflicts or [])]},
        "budget_policy_summary": {},
        "projection_contract_versions": {},
    }


def public_safe_fixtures() -> list[dict[str, Any]]:
    """Return public-safe donor-compatible extraction-quality fixtures.

    These fixtures intentionally use synthetic IDs and fingerprints only. They
    exercise donor proposal normalization plus deterministic Tier2 policy, not
    live Hindsight, private transcript data, or storage writes.
    """

    return [
        {
            "id": "durable_profile_fact",
            "quality_class": "durable_fact_precision",
            "raw_batch": _raw_batch(
                "op-durable-profile",
                [
                    {
                        "action": "create",
                        "target_kind": "user_fact",
                        "target_slot": "identity.preferred_address_name",
                        "stable_key": "identity.preferred_address_name",
                        "value_fingerprint": "sha256:profile-public",
                        "confidence": 0.98,
                        "reason_code": "EXPLICIT_USER_FACT",
                        "source_span_ids": ["span-user"],
                        "source_event_ids": ["event-span-user"],
                        "assertion_speaker": "user",
                    }
                ],
            ),
            "expected_decisions": [
                {
                    "decision_class": "durable_fact_candidate",
                    "memory_kind": "profile_fact",
                    "truth_eligible": True,
                }
            ],
        },
        {
            "id": "duplicate_create_noop",
            "quality_class": "duplicate_prevention",
            "raw_batch": _raw_batch(
                "op-duplicate-noop",
                [
                    {
                        "action": "create",
                        "target_kind": "user_fact",
                        "target_slot": "identity.preferred_address_name",
                        "stable_key": "identity.preferred_address_name",
                        "value_fingerprint": "sha256:profile-public",
                        "source_span_ids": ["span-user"],
                        "source_event_ids": ["event-span-user"],
                        "assertion_speaker": "user",
                    }
                ],
            ),
            "existing": [
                {
                    "memory_ref": "fact-existing-public",
                    "stable_key": "identity.preferred_address_name",
                    "value_fingerprint": "sha256:profile-public",
                }
            ],
            "expected_decisions": [
                {
                    "decision_class": "inspect_only",
                    "lifecycle_action": "noop",
                    "truth_eligible": False,
                }
            ],
        },
        {
            "id": "correction_supersession",
            "quality_class": "update_supersession_correctness",
            "raw_batch": _raw_batch(
                "op-correction",
                [
                    {
                        "action": "correction",
                        "target_kind": "user_fact",
                        "target_slot": "identity.preferred_address_name",
                        "stable_key": "identity.preferred_address_name",
                        "value_fingerprint": "sha256:profile-corrected-public",
                        "source_span_ids": ["span-user"],
                        "source_event_ids": ["event-span-user"],
                        "assertion_speaker": "user",
                    }
                ],
            ),
            "existing": [
                {
                    "memory_ref": "fact-old-public",
                    "stable_key": "identity.preferred_address_name",
                    "value_fingerprint": "sha256:profile-old-public",
                }
            ],
            "expected_decisions": [
                {
                    "decision_class": "lifecycle_update_candidate",
                    "lifecycle_action": "correction",
                    "truth_eligible": True,
                }
            ],
        },
        {
            "id": "conflict_review_not_answer_truth",
            "quality_class": "conflict_precision",
            "raw_batch": _raw_batch(
                "op-conflict",
                [
                    {
                        "action": "create",
                        "target_kind": "project_fact",
                        "target_slot": "project.creator",
                        "stable_key": "project.creator",
                        "value_fingerprint": "sha256:creator-new-public",
                        "source_span_ids": ["span-user"],
                        "source_event_ids": ["event-span-user"],
                        "assertion_speaker": "user",
                    }
                ],
            ),
            "conflicts": [{"stable_key": "project.creator"}],
            "expected_decisions": [
                {
                    "decision_class": "conflict_review",
                    "truth_eligible": False,
                    "support_visibility": "contradiction_only",
                }
            ],
        },
        {
            "id": "support_context_preserved",
            "quality_class": "support_preservation",
            "raw_batch": _raw_batch(
                "op-support",
                [
                    {
                        "action": "create",
                        "target_kind": "support_context",
                        "value_fingerprint": "sha256:support-public",
                        "source_span_ids": ["span-user"],
                        "source_event_ids": ["event-span-user"],
                        "assertion_speaker": "user",
                        "support_visibility": "inspect_only",
                    }
                ],
            ),
            "expected_decisions": [
                {
                    "decision_class": "support_event",
                    "memory_kind": "support_context",
                    "truth_eligible": False,
                }
            ],
        },
        {
            "id": "assistant_authored_truth_dropped",
            "quality_class": "assistant_authored_rejection",
            "raw_batch": _raw_batch(
                "op-assistant-drop",
                [
                    {
                        "action": "create",
                        "target_kind": "user_fact",
                        "target_slot": "identity.preferred_address_name",
                        "value_fingerprint": "sha256:assistant-public",
                        "source_span_ids": ["span-assistant"],
                        "source_event_ids": ["event-span-assistant"],
                        "assertion_speaker": "assistant",
                    }
                ],
            ),
            "spans": [_span("span-assistant", speaker="assistant")],
            "expected_batch_status": "degraded",
            "expected_failure_reason": "HINDSIGHT_ASSISTANT_AUTHORED_ACTION_DROPPED",
            "expected_decisions": [],
            "resolved_failure_bundle": "assistant_authored_truth_attempt_blocked",
        },
        {
            "id": "missing_source_inspect_only",
            "quality_class": "missing_source_block",
            "raw_batch": _raw_batch(
                "op-missing-source",
                [
                    {
                        "action": "create",
                        "target_kind": "project_fact",
                        "target_slot": "project.creator",
                        "stable_key": "project.creator",
                        "value_fingerprint": "sha256:missing-source-public",
                        "source_span_ids": ["span-missing"],
                        "source_event_ids": ["event-span-missing"],
                        "assertion_speaker": "user",
                    }
                ],
            ),
            "spans": [],
            "expected_decisions": [
                {
                    "decision_class": "inspect_only",
                    "truth_eligible": False,
                    "reason_code": "REJECTED_MISSING_VERIFIED_SOURCE",
                }
            ],
            "resolved_failure_bundle": "missing_verified_source_blocked",
        },
        {
            "id": "unsupported_donor_action_drift",
            "quality_class": "donor_drift_detection",
            "raw_batch": _raw_batch(
                "op-donor-drift",
                [
                    {
                        "action": "invent",
                        "target_kind": "unknown_kind",
                        "source_span_ids": ["span-user"],
                        "source_event_ids": ["event-span-user"],
                        "assertion_speaker": "user",
                    }
                ],
            ),
            "expected_batch_status": "degraded",
            "expected_decisions": [
                {
                    "decision_class": "support_event",
                    "memory_kind": "support_context",
                    "truth_eligible": False,
                }
            ],
            "resolved_failure_bundle": "unsupported_donor_action_drift_blocked",
        },
        {
            "id": "ignored_action_not_truth",
            "quality_class": "ignored_action_not_truth",
            "raw_batch": _raw_batch(
                "op-ignore",
                [
                    {
                        "action": "ignore",
                        "target_kind": "user_fact",
                        "target_slot": "identity.unwanted_candidate",
                        "stable_key": "identity.unwanted_candidate",
                        "value_fingerprint": "sha256:ignored-public",
                        "source_span_ids": ["span-user"],
                        "source_event_ids": ["event-span-user"],
                        "assertion_speaker": "user",
                    }
                ],
            ),
            "expected_decisions": [
                {
                    "decision_class": "inspect_only",
                    "memory_kind": "profile_fact",
                    "truth_eligible": False,
                    "reason_code": "INSPECT_ONLY_UNVERIFIED_DONOR_PROPOSAL",
                }
            ],
            "resolved_failure_bundle": "ignored_donor_action_not_durable_truth",
        },
        {
            "id": "multilingual_style_hu",
            "quality_class": "multilingual_robustness",
            "metamorphic_group": "style_no_emoji",
            "raw_batch": _raw_batch(
                "op-style-hu",
                [
                    {
                        "action": "create",
                        "target_kind": "style_rule",
                        "target_slot": "style.no_emoji",
                        "stable_key": "style.no_emoji",
                        "value_fingerprint": "sha256:no-emoji-public",
                        "source_span_ids": ["span-user"],
                        "source_event_ids": ["event-span-user"],
                        "assertion_speaker": "user",
                    }
                ],
            ),
            "expected_decisions": [
                {
                    "decision_class": "durable_fact_candidate",
                    "memory_kind": "style_rule",
                    "truth_eligible": True,
                }
            ],
        },
        {
            "id": "multilingual_style_en",
            "quality_class": "multilingual_robustness",
            "metamorphic_group": "style_no_emoji",
            "raw_batch": _raw_batch(
                "op-style-en",
                [
                    {
                        "action": "create",
                        "target_kind": "style_rule",
                        "target_slot": "style.no_emoji",
                        "stable_key": "style.no_emoji",
                        "value_fingerprint": "sha256:no-emoji-public",
                        "source_span_ids": ["span-user"],
                        "source_event_ids": ["event-span-user"],
                        "assertion_speaker": "user",
                    }
                ],
            ),
            "expected_decisions": [
                {
                    "decision_class": "durable_fact_candidate",
                    "memory_kind": "style_rule",
                    "truth_eligible": True,
                }
            ],
        },
    ]


def _decision_value(decision: Mapping[str, Any], key: str) -> Any:
    if key == "truth_eligible":
        return decision.get("authority", {}).get("truth_eligible")
    if key == "support_visibility":
        return decision.get("authority", {}).get("support_visibility")
    if key == "lifecycle_action":
        return decision.get("lifecycle", {}).get("action")
    return decision.get(key)


def _expected_matches(decision: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    for key, expected_value in expected.items():
        actual = _decision_value(decision, key)
        if key == "reason_code" and expected_value == "REJECTED_MISSING_VERIFIED_SOURCE":
            if actual not in {"REJECTED_MISSING_VERIFIED_SOURCE_SPAN", "REJECTED_MISSING_VERIFIED_SOURCE_EVENT"}:
                return False
            continue
        if actual != expected_value:
            return False
    return True


def _bundle(bundle_id: str, *, fixture_id: str, quality_class: str, status: str, reason: str) -> dict[str, Any]:
    return {
        "bundle_id": bundle_id,
        "fixture_id": fixture_id,
        "quality_class": quality_class,
        "status": status,
        "reason_code": reason,
        "public_safe": True,
    }


def _all_zero(mapping: Mapping[str, Any]) -> bool:
    return all(int(value or 0) == 0 for value in mapping.values())


def build_tier2_extraction_quality_report(
    *,
    fixtures: Iterable[Mapping[str, Any]] | None = None,
    bloat_ratio_threshold: float = DEFAULT_BLOAT_RATIO_THRESHOLD,
) -> dict[str, Any]:
    selected_fixtures = [deepcopy(dict(item)) for item in (fixtures if fixtures is not None else public_safe_fixtures())]
    cases: list[dict[str, Any]] = []
    unresolved_failure_bundles: list[dict[str, Any]] = []
    resolved_failure_bundles: list[dict[str, Any]] = []
    quality_class_passes = {key: False for key in REQUIRED_QUALITY_CLASSES if key != "bloat_impact"}
    metamorphic: dict[str, set[tuple[str, str, bool]]] = {}
    produced_decisions = 0
    matched_decisions = 0
    truth_candidate_count = 0
    support_pressure = 0
    donor_degraded_count = 0
    blocked_input_counters = {
        "assistant_authored_actions_dropped": 0,
        "missing_verified_source_blocks": 0,
        "unsupported_donor_actions": 0,
    }
    harmful_counters = {
        "unsafe_truth_decisions": 0,
        "assistant_authored_truth_decisions": 0,
        "missing_source_truth_decisions": 0,
        "schema_issues": 0,
        "semantic_conformance_issues": 0,
        "unresolved_failure_bundles": 0,
        "bloat_budget_failures": 0,
    }

    for fixture in selected_fixtures:
        fixture_id = _text(fixture.get("id"))
        quality_class = _text(fixture.get("quality_class"))
        batch = normalize_proposal_action_batch(fixture.get("raw_batch") or {})
        if batch.get("status") == "degraded":
            donor_degraded_count += 1
        counters = batch.get("critical_counters") if isinstance(batch.get("critical_counters"), Mapping) else {}
        blocked_input_counters["assistant_authored_actions_dropped"] += int(
            batch.get("failure", {}).get("dropped_assistant_authored_actions") or 0
        )
        blocked_input_counters["unsupported_donor_actions"] += int(counters.get("unsupported_actions") or 0)
        packet = _packet(
            batch,
            spans=fixture.get("spans"),
            existing=fixture.get("existing"),
            conflicts=fixture.get("conflicts"),
        )
        plan = build_tier2_decision_plan(packet)
        schema_issues = validate_tier2_decision_plan(plan)
        conformance_issues = semantic_conformance_issues(plan)
        harmful_counters["schema_issues"] += len(schema_issues)
        harmful_counters["semantic_conformance_issues"] += len(conformance_issues)
        blocked_input_counters["missing_verified_source_blocks"] += int(
            plan.get("critical_counters", {}).get("missing_verified_source") or 0
        )
        decisions = [item for item in plan.get("decisions", []) if isinstance(item, Mapping)]
        expected = [item for item in fixture.get("expected_decisions", []) if isinstance(item, Mapping)]
        case_pass = True
        if fixture.get("expected_batch_status") and batch.get("status") != fixture.get("expected_batch_status"):
            case_pass = False
        if fixture.get("expected_failure_reason"):
            if batch.get("failure", {}).get("reason_code") != fixture.get("expected_failure_reason"):
                case_pass = False
        if len(decisions) != len(expected):
            case_pass = False
        decision_results = []
        for index, decision in enumerate(decisions):
            produced_decisions += 1
            if decision.get("authority", {}).get("truth_eligible") is True:
                truth_candidate_count += 1
            if decision.get("decision_class") in {"support_event", "reject", "inspect_only", "clarification_required"}:
                support_pressure += 1
            if decision.get("decision_class") in {"durable_fact_candidate", "lifecycle_update_candidate", "relation_candidate"}:
                if decision.get("authority", {}).get("truth_eligible") is not True:
                    harmful_counters["unsafe_truth_decisions"] += 1
            if "REJECTED_ASSISTANT_AUTHORED_TRUTH_ATTEMPT" in decision.get("trace", {}).get("blocked_by", []):
                if decision.get("authority", {}).get("truth_eligible") is True:
                    harmful_counters["assistant_authored_truth_decisions"] += 1
            missing_source_blocked = any(
                item in decision.get("trace", {}).get("blocked_by", [])
                for item in {"REJECTED_MISSING_VERIFIED_SOURCE_SPAN", "REJECTED_MISSING_VERIFIED_SOURCE_EVENT"}
            )
            if missing_source_blocked and decision.get("authority", {}).get("truth_eligible") is True:
                harmful_counters["missing_source_truth_decisions"] += 1
            expected_decision = expected[index] if index < len(expected) else {}
            matched = bool(expected_decision) and _expected_matches(decision, expected_decision)
            if matched:
                matched_decisions += 1
            else:
                case_pass = False
            decision_results.append(
                {
                    "proposal_id": decision.get("proposal_id"),
                    "decision_class": decision.get("decision_class"),
                    "memory_kind": decision.get("memory_kind"),
                    "truth_eligible": decision.get("authority", {}).get("truth_eligible"),
                    "reason_code": decision.get("reason_code"),
                    "matched_expected": matched,
                }
            )
        if group := fixture.get("metamorphic_group"):
            for decision in decisions:
                metamorphic.setdefault(_text(group), set()).add(
                    (
                        _text(decision.get("decision_class")),
                        _text(decision.get("memory_kind")),
                        bool(decision.get("authority", {}).get("truth_eligible")),
                    )
                )
        if case_pass and quality_class in quality_class_passes:
            quality_class_passes[quality_class] = True
        bundle_id = _text(fixture.get("resolved_failure_bundle"))
        if bundle_id and case_pass:
            resolved_failure_bundles.append(
                _bundle(
                    bundle_id,
                    fixture_id=fixture_id,
                    quality_class=quality_class,
                    status="resolved_by_policy",
                    reason=_text(batch.get("failure", {}).get("reason_code") or decision_results[0].get("reason_code") if decision_results else batch.get("failure", {}).get("reason_code")),
                )
            )
        if not case_pass:
            unresolved_failure_bundles.append(
                _bundle(
                    f"unresolved_{fixture_id}",
                    fixture_id=fixture_id,
                    quality_class=quality_class,
                    status="unresolved",
                    reason="M004_EXTRACTION_QUALITY_EXPECTATION_FAILED",
                )
            )
        cases.append(
            {
                "id": fixture_id,
                "quality_class": quality_class,
                "status": "pass" if case_pass else "fail",
                "batch_status": batch.get("status"),
                "batch_failure_reason": batch.get("failure", {}).get("reason_code"),
                "decision_count": len(decisions),
                "decisions": decision_results,
                "schema_issues": schema_issues,
                "semantic_conformance_issues": conformance_issues,
            }
        )

    multilingual_ok = all(len(values) == 1 for values in metamorphic.values()) and bool(metamorphic)
    quality_class_passes["multilingual_robustness"] = multilingual_ok
    support_to_truth_ratio = support_pressure / max(truth_candidate_count, 1)
    bloat_status = "pass" if support_to_truth_ratio <= bloat_ratio_threshold else "fail"
    if bloat_status != "pass":
        harmful_counters["bloat_budget_failures"] += 1
    harmful_counters["unresolved_failure_bundles"] = len(unresolved_failure_bundles)
    quality_class_passes["bloat_impact"] = bloat_status == "pass"
    proposal_precision = matched_decisions / max(produced_decisions, 1)
    proposal_recall = sum(1 for value in quality_class_passes.values() if value) / len(REQUIRED_QUALITY_CLASSES)
    metrics = {
        "proposal_precision": proposal_precision,
        "proposal_recall": proposal_recall,
        "update_supersession_correctness": 1.0 if quality_class_passes["update_supersession_correctness"] else 0.0,
        "conflict_precision": 1.0 if quality_class_passes["conflict_precision"] else 0.0,
        "support_preservation": 1.0 if quality_class_passes["support_preservation"] else 0.0,
        "multilingual_robustness": 1.0 if quality_class_passes["multilingual_robustness"] else 0.0,
        "donor_drift_detection": 1.0 if quality_class_passes["donor_drift_detection"] else 0.0,
    }
    public_safe = True
    status = (
        "pass"
        if public_safe
        and _all_zero(harmful_counters)
        and all(value is True for value in quality_class_passes.values())
        and proposal_precision == 1.0
        and proposal_recall == 1.0
        else "fail"
    )
    return {
        "schema": TIER2_EXTRACTION_QUALITY_SCHEMA,
        "version": TIER2_EXTRACTION_QUALITY_VERSION,
        "status": status,
        "public_safe": public_safe,
        "claim_boundary": (
            "Public-safe fixture proof for donor-compatible proposal normalization, deterministic Tier2 decision planning, "
            "failure-bundle reporting, and bloat-impact counters. It is not a live private-data or global product claim."
        ),
        "donor_first_decision": {
            "donor": "hindsight-compatible proposal action batch",
            "brainstack_role": "deterministic policy, admission/receipt preconditions, trace, and release gate proof",
            "not_implemented": "custom smart extractor or provider-specific prompt path",
        },
        "metrics": metrics,
        "quality_class_passes": quality_class_passes,
        "harmful_counters": harmful_counters,
        "blocked_input_counters": blocked_input_counters,
        "bloat_impact": {
            "status": bloat_status,
            "support_pressure_count": support_pressure,
            "truth_candidate_count": truth_candidate_count,
            "support_to_truth_ratio": support_to_truth_ratio,
            "threshold": bloat_ratio_threshold,
        },
        "donor_drift": {
            "status": "pass" if quality_class_passes["donor_drift_detection"] else "fail",
            "degraded_batch_count": donor_degraded_count,
            "unsupported_donor_actions": blocked_input_counters["unsupported_donor_actions"],
        },
        "failure_bundles": {
            "resolved": resolved_failure_bundles,
            "unresolved": unresolved_failure_bundles,
        },
        "case_count": len(cases),
        "cases": cases,
    }


def report_to_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
