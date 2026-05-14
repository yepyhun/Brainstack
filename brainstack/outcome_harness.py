from __future__ import annotations

import json
import math
from copy import deepcopy
from typing import Any, Iterable, Mapping

from .memory_use_record import build_memory_use_record, validate_memory_use_record

REPORT_SCHEMA = "brainstack.memory_outcome_harness_report.v1"

MODES = ("memory_off", "raw_history", "brainstack_packet")

METRIC_NAMES = (
    "answer_correct",
    "continuity_success",
    "repeated_explanation_avoided",
    "stale_or_forbidden_selected_count",
    "scope_bleed_count",
    "provenance_available",
    "inspect_route_available",
    "model_facing_memory_tokens",
    "raw_history_tokens",
    "token_delta_vs_raw_history",
    "used_in_answer",
    "correction_needed",
)

PRIVATE_RUNTIME_MARKERS = (
    "/private/runtime/path",
    "private_user_handle",
    "private_agent_name",
    "private_project_code",
    "private_chat_platform",
    "private_container_name",
)


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _repeat(text: str, count: int) -> str:
    return " ".join(text for _ in range(count))


def _evidence(
    evidence_id: str,
    *,
    text: str,
    scope: str = "shared_public",
    lifecycle: str = "current",
    provenance: str = "receipt:synthetic",
    supports_expected: bool = False,
    forbidden_as_authority: bool = False,
) -> dict[str, Any]:
    return {
        "id": evidence_id,
        "text": text,
        "scope": scope,
        "lifecycle": lifecycle,
        "provenance": provenance,
        "supports_expected": supports_expected,
        "forbidden_as_authority": forbidden_as_authority,
    }


def _mode(
    *,
    packet: str,
    answer: str,
    selected_evidence: Iterable[str] = (),
    provenance_refs: Iterable[str] = (),
    inspect_route_available: bool = False,
    asks_user_to_repeat: bool = False,
) -> dict[str, Any]:
    return {
        "packet": packet,
        "answer": answer,
        "selected_evidence": list(selected_evidence),
        "provenance_refs": list(provenance_refs),
        "inspect_route_available": inspect_route_available,
        "asks_user_to_repeat": asks_user_to_repeat,
    }


def default_harness_cases() -> list[dict[str, Any]]:
    preference_history = _repeat(
        "The user prefers concise implementation notes, concrete file paths, "
        "and verification evidence before a task is called done.",
        34,
    )
    current_truth_history = _repeat(
        "Yesterday the user was hungry during a planning session. Later the "
        "user explicitly said they are not hungry now. Older appetite state "
        "must not be treated as current truth.",
        32,
    )
    project_history = _repeat(
        "The team rejected adapter Alpha after a migration review and chose "
        "adapter Beta for the public import path. The decision must survive "
        "restart and compression.",
        30,
    )
    source_history = _repeat(
        "Policy Manual section 4.2 says backups run every six hours and must "
        "include a retention receipt. The agent should cite the manual section.",
        28,
    )
    profile_history = _repeat(
        "Profile Alpha prefers metric units. Profile Beta prefers imperial "
        "units. Private profile settings must not cross scopes.",
        36,
    )
    inspect_history = _repeat(
        "The memory packet should expose receipts, source references, and an "
        "inspect route so the agent can explain why it believes a fact.",
        24,
    )

    return [
        {
            "id": "preference_continuity",
            "title": "Returning preference continuity",
            "allowed_scopes": ["profile_alpha", "shared_public"],
            "requires_prior_memory": True,
            "requires_provenance": True,
            "expected_answer_terms": ["concise", "file paths", "verification"],
            "forbidden_answer_terms": ["repeat"],
            "evidence": [
                _evidence(
                    "profile_alpha_pref_current",
                    text="Profile Alpha prefers concise implementation notes, concrete file paths, and verification evidence.",
                    scope="profile_alpha",
                    provenance="receipt:pref-001",
                    supports_expected=True,
                )
            ],
            "raw_history_packet": preference_history,
            "modes": {
                "memory_off": _mode(
                    packet="",
                    answer="Please repeat your preferred working style.",
                    asks_user_to_repeat=True,
                ),
                "raw_history": _mode(
                    packet=preference_history,
                    answer="You prefer concise implementation notes with concrete file paths and verification evidence.",
                    selected_evidence=["profile_alpha_pref_current"],
                ),
                "brainstack_packet": _mode(
                    packet="profile_alpha_pref_current: concise implementation notes; concrete file paths; verification evidence; receipt:pref-001",
                    answer="Use concise implementation notes, concrete file paths, and verification evidence.",
                    selected_evidence=["profile_alpha_pref_current"],
                    provenance_refs=["receipt:pref-001"],
                    inspect_route_available=True,
                ),
            },
        },
        {
            "id": "current_truth_supersession",
            "title": "Changed current truth supersession",
            "allowed_scopes": ["profile_alpha", "shared_public"],
            "requires_prior_memory": True,
            "requires_provenance": True,
            "expected_answer_terms": ["not hungry now"],
            "forbidden_answer_terms": ["may be hungry now"],
            "evidence": [
                _evidence(
                    "appetite_prior",
                    text="The user was hungry yesterday.",
                    scope="profile_alpha",
                    lifecycle="superseded",
                    provenance="receipt:state-010",
                    forbidden_as_authority=True,
                ),
                _evidence(
                    "appetite_current",
                    text="The user is not hungry now.",
                    scope="profile_alpha",
                    provenance="receipt:state-011",
                    supports_expected=True,
                ),
            ],
            "raw_history_packet": current_truth_history,
            "modes": {
                "memory_off": _mode(packet="", answer="I do not know the current appetite state."),
                "raw_history": _mode(
                    packet=current_truth_history,
                    answer="The record says the user was hungry yesterday, so they may be hungry now.",
                    selected_evidence=["appetite_prior"],
                ),
                "brainstack_packet": _mode(
                    packet="current_truth: appetite_current = not hungry now; supersedes appetite_prior; receipt:state-011",
                    answer="The current truth is that the user is not hungry now.",
                    selected_evidence=["appetite_current"],
                    provenance_refs=["receipt:state-011"],
                    inspect_route_available=True,
                ),
            },
        },
        {
            "id": "project_decision_recall",
            "title": "Long-running project decision recall",
            "allowed_scopes": ["project_delta", "shared_public"],
            "requires_prior_memory": True,
            "requires_provenance": True,
            "expected_answer_terms": ["adapter beta", "public import path"],
            "forbidden_answer_terms": ["adapter alpha is chosen"],
            "evidence": [
                _evidence(
                    "decision_old_alpha",
                    text="Adapter Alpha was considered first.",
                    scope="project_delta",
                    lifecycle="superseded",
                    provenance="receipt:decision-019",
                    forbidden_as_authority=True,
                ),
                _evidence(
                    "decision_beta_current",
                    text="Adapter Beta is the accepted public import path.",
                    scope="project_delta",
                    provenance="receipt:decision-020",
                    supports_expected=True,
                ),
            ],
            "raw_history_packet": project_history,
            "modes": {
                "memory_off": _mode(packet="", answer="I need the decision repeated before proceeding.", asks_user_to_repeat=True),
                "raw_history": _mode(
                    packet=project_history,
                    answer="Adapter Beta was chosen for the public import path.",
                    selected_evidence=["decision_beta_current"],
                ),
                "brainstack_packet": _mode(
                    packet="project_delta current decision: adapter Beta for public import path; old Alpha rejected; receipt:decision-020",
                    answer="Proceed with adapter Beta for the public import path.",
                    selected_evidence=["decision_beta_current"],
                    provenance_refs=["receipt:decision-020"],
                    inspect_route_available=True,
                ),
            },
        },
        {
            "id": "source_backed_document_recall",
            "title": "Source-backed document recall",
            "allowed_scopes": ["shared_public"],
            "requires_prior_memory": True,
            "requires_provenance": True,
            "expected_answer_terms": ["six hours", "section 4.2"],
            "forbidden_answer_terms": ["daily"],
            "evidence": [
                _evidence(
                    "manual_42_backup",
                    text="Policy Manual section 4.2 says backups run every six hours.",
                    provenance="doc:policy-manual#4.2",
                    supports_expected=True,
                )
            ],
            "raw_history_packet": source_history,
            "modes": {
                "memory_off": _mode(packet="", answer="I need the policy text again.", asks_user_to_repeat=True),
                "raw_history": _mode(
                    packet=source_history,
                    answer="Policy Manual section 4.2 says backups run every six hours.",
                    selected_evidence=["manual_42_backup"],
                ),
                "brainstack_packet": _mode(
                    packet="corpus cite doc:policy-manual#4.2: backups run every six hours",
                    answer="Policy Manual section 4.2 says backups run every six hours.",
                    selected_evidence=["manual_42_backup"],
                    provenance_refs=["doc:policy-manual#4.2"],
                    inspect_route_available=True,
                ),
            },
        },
        {
            "id": "multi_profile_isolation",
            "title": "Multi-profile isolation",
            "allowed_scopes": ["profile_alpha", "shared_public"],
            "requires_prior_memory": True,
            "requires_provenance": True,
            "expected_answer_terms": ["metric units"],
            "forbidden_answer_terms": ["imperial units"],
            "evidence": [
                _evidence(
                    "profile_alpha_units",
                    text="Profile Alpha prefers metric units.",
                    scope="profile_alpha",
                    provenance="receipt:profile-alpha-003",
                    supports_expected=True,
                ),
                _evidence(
                    "profile_beta_units",
                    text="Profile Beta prefers imperial units.",
                    scope="profile_beta",
                    provenance="receipt:profile-beta-008",
                    forbidden_as_authority=True,
                ),
            ],
            "raw_history_packet": profile_history,
            "modes": {
                "memory_off": _mode(packet="", answer="I do not know this profile's unit preference."),
                "raw_history": _mode(
                    packet=profile_history,
                    answer="Profile Alpha may prefer metric units, but another profile prefers imperial units.",
                    selected_evidence=["profile_alpha_units", "profile_beta_units"],
                ),
                "brainstack_packet": _mode(
                    packet="scope profile_alpha only: prefers metric units; receipt:profile-alpha-003",
                    answer="Use metric units for Profile Alpha.",
                    selected_evidence=["profile_alpha_units"],
                    provenance_refs=["receipt:profile-alpha-003"],
                    inspect_route_available=True,
                ),
            },
        },
        {
            "id": "inspectability_receipt_route",
            "title": "Inspectable receipt route",
            "allowed_scopes": ["shared_public"],
            "requires_prior_memory": True,
            "requires_provenance": True,
            "expected_answer_terms": ["receipt", "inspect route"],
            "forbidden_answer_terms": ["cannot explain"],
            "evidence": [
                _evidence(
                    "inspect_receipt_contract",
                    text="Memory answers should carry a receipt and an inspect route.",
                    provenance="receipt:inspect-001",
                    supports_expected=True,
                )
            ],
            "raw_history_packet": inspect_history,
            "modes": {
                "memory_off": _mode(packet="", answer="I cannot explain why I believe that."),
                "raw_history": _mode(
                    packet=inspect_history,
                    answer="The notes mention receipts, but no structured inspect route is available.",
                    selected_evidence=["inspect_receipt_contract"],
                ),
                "brainstack_packet": _mode(
                    packet="receipt:inspect-001; inspect_route=memory.inspect(record_id=inspect_receipt_contract)",
                    answer="The answer has receipt:inspect-001 and an inspect route for the selected record.",
                    selected_evidence=["inspect_receipt_contract"],
                    provenance_refs=["receipt:inspect-001"],
                    inspect_route_available=True,
                ),
            },
        },
    ]


def _answer_correct(case: Mapping[str, Any], answer: str) -> bool:
    answer_lower = answer.lower()
    expected = [str(term).lower() for term in case["expected_answer_terms"]]
    forbidden = [str(term).lower() for term in case["forbidden_answer_terms"]]
    return all(term in answer_lower for term in expected) and not any(term in answer_lower for term in forbidden)


def _score_mode(case: Mapping[str, Any], mode_name: str, mode: Mapping[str, Any]) -> dict[str, Any]:
    evidence_by_id = {item["id"]: item for item in case["evidence"]}
    selected = [evidence_by_id[item_id] for item_id in mode["selected_evidence"] if item_id in evidence_by_id]
    allowed_scopes = set(case["allowed_scopes"])
    answer_correct = _answer_correct(case, str(mode["answer"]))
    stale_or_forbidden = sum(
        1
        for item in selected
        if item.get("lifecycle") in {"stale", "superseded", "rejected"}
        or bool(item.get("forbidden_as_authority"))
    )
    scope_bleed = sum(
        1 for item in selected if str(item.get("scope") or "") not in allowed_scopes
    )
    provenance_refs = [str(ref) for ref in mode.get("provenance_refs") or [] if str(ref)]
    provenance_available = bool(provenance_refs) if case["requires_provenance"] else "not_applicable"
    used_in_answer = answer_correct and any(bool(item.get("supports_expected")) for item in selected)
    packet_tokens = _estimate_tokens(str(mode.get("packet") or ""))
    raw_tokens = _estimate_tokens(str(case["raw_history_packet"]))

    metrics = {
        "answer_correct": answer_correct,
        "continuity_success": bool(case["requires_prior_memory"]) and answer_correct,
        "repeated_explanation_avoided": answer_correct and not bool(mode.get("asks_user_to_repeat")),
        "stale_or_forbidden_selected_count": stale_or_forbidden,
        "scope_bleed_count": scope_bleed,
        "provenance_available": provenance_available,
        "inspect_route_available": bool(mode.get("inspect_route_available")),
        "model_facing_memory_tokens": packet_tokens,
        "raw_history_tokens": raw_tokens,
        "token_delta_vs_raw_history": packet_tokens - raw_tokens,
        "used_in_answer": used_in_answer,
        "correction_needed": (not answer_correct) or stale_or_forbidden > 0 or scope_bleed > 0,
    }
    memory_use_record = build_memory_use_record(
        consumer_id=f"outcome_harness:{mode_name}",
        task_id=str(case["id"]),
        source_packet_id=f"{case['id']}:{mode_name}",
        selected_memory_ids=mode["selected_evidence"],
        used_memory_ids=[item["id"] for item in selected if bool(item.get("supports_expected")) and answer_correct],
        ignored_memory_ids=[
            item["id"]
            for item in selected
            if not (bool(item.get("supports_expected")) and answer_correct)
        ],
        provenance_refs=provenance_refs,
        outcome_metrics={
            "answer_correct": answer_correct,
            "used_in_answer": used_in_answer,
            "stale_or_forbidden_selected_count": stale_or_forbidden,
            "scope_bleed_count": scope_bleed,
        },
    )
    memory_use_record_validation = validate_memory_use_record(memory_use_record)
    return {
        "mode": mode_name,
        "answer": mode["answer"],
        "selected_evidence": list(mode["selected_evidence"]),
        "metrics": metrics,
        "memory_use_record": memory_use_record,
        "memory_use_record_validation": memory_use_record_validation,
    }


def _score_case(case: Mapping[str, Any]) -> dict[str, Any]:
    results = {mode: _score_mode(case, mode, case["modes"][mode]) for mode in MODES}
    return {
        "id": case["id"],
        "title": case["title"],
        "expected_answer_terms": list(case["expected_answer_terms"]),
        "forbidden_answer_terms": list(case["forbidden_answer_terms"]),
        "allowed_scopes": list(case["allowed_scopes"]),
        "results": results,
    }


def _public_safe(report: Mapping[str, Any]) -> bool:
    text = json.dumps(report, sort_keys=True)
    return not any(marker in text for marker in PRIVATE_RUNTIME_MARKERS)


def build_report(case_ids: Iterable[str] | None = None) -> dict[str, Any]:
    selected_ids = set(case_ids or [])
    cases = [
        case
        for case in deepcopy(default_harness_cases())
        if not selected_ids or case["id"] in selected_ids
    ]
    scored_cases = [_score_case(case) for case in cases]

    brainstack_results = [case["results"]["brainstack_packet"]["metrics"] for case in scored_cases]
    raw_history_results = [case["results"]["raw_history"]["metrics"] for case in scored_cases]
    memory_off_results = [case["results"]["memory_off"]["metrics"] for case in scored_cases]

    metric_keys_complete = all(
        set(case["results"][mode]["metrics"]) == set(METRIC_NAMES)
        for case in scored_cases
        for mode in MODES
    )
    memory_use_records_valid = all(
        case["results"][mode]["memory_use_record_validation"] == []
        and case["results"][mode]["memory_use_record"]["truth_eligible"] is False
        and case["results"][mode]["memory_use_record"]["model_facing_default"] is False
        for case in scored_cases
        for mode in MODES
    )
    all_modes_present = all(set(case["results"]) == set(MODES) for case in scored_cases)
    brainstack_negative_invariants_hold = all(
        metrics["stale_or_forbidden_selected_count"] == 0
        and metrics["scope_bleed_count"] == 0
        and metrics["answer_correct"] is True
        and metrics["correction_needed"] is False
        for metrics in brainstack_results
    )
    raw_history_correct_count = sum(1 for metrics in raw_history_results if metrics["answer_correct"] is True)
    memory_off_correct_count = sum(1 for metrics in memory_off_results if metrics["answer_correct"] is True)
    brainstack_token_savings_cases = sum(
        1 for metrics in brainstack_results if int(metrics["token_delta_vs_raw_history"]) < 0
    )

    summary = {
        "brainstack_answer_correct_count": sum(1 for metrics in brainstack_results if metrics["answer_correct"] is True),
        "raw_history_answer_correct_count": raw_history_correct_count,
        "memory_off_answer_correct_count": memory_off_correct_count,
        "brainstack_token_savings_cases": brainstack_token_savings_cases,
        "brainstack_scope_bleed_count": sum(int(metrics["scope_bleed_count"]) for metrics in brainstack_results),
        "brainstack_stale_or_forbidden_count": sum(
            int(metrics["stale_or_forbidden_selected_count"]) for metrics in brainstack_results
        ),
    }
    proof = {
        "all_modes_present": all_modes_present,
        "metric_keys_complete": metric_keys_complete,
        "brainstack_negative_invariants_hold": brainstack_negative_invariants_hold,
        "raw_history_baseline_represented": raw_history_correct_count >= 3,
        "memory_off_baseline_represented": len(memory_off_results) == len(scored_cases),
        "brainstack_token_savings_observed": brainstack_token_savings_cases >= 4,
        "memory_use_records_valid": memory_use_records_valid,
        "deterministic_no_llm_calls": True,
    }
    report = {
        "schema": REPORT_SCHEMA,
        "status": "unknown",
        "public_safe": False,
        "read_only": True,
        "side_effect_free": True,
        "llm_calls_performed": False,
        "harness_count": len(scored_cases),
        "mode_count": len(MODES),
        "summary": summary,
        "cases": scored_cases,
        "issues": [],
        "proof": proof,
    }
    public_safe = _public_safe(report)
    report["public_safe"] = public_safe
    report["proof"]["public_safe_report"] = public_safe
    if not selected_ids and len(scored_cases) < 5:
        report["issues"].append("default_harness_count_below_contract")
    if selected_ids and selected_ids - {case["id"] for case in cases}:
        report["issues"].append("unknown_case_id_requested")

    report["status"] = "pass" if all(report["proof"].values()) and not report["issues"] else "fail"
    return report


def run_harness(case_ids: Iterable[str] | None = None) -> dict[str, Any]:
    return build_report(case_ids=case_ids)


__all__ = ["METRIC_NAMES", "MODES", "REPORT_SCHEMA", "build_report", "default_harness_cases", "run_harness"]
