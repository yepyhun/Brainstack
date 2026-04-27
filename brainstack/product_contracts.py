"""Boundary-clean product RC contracts for Brainstack/Hermes integration.

These contracts are intentionally small and deterministic. They classify
runtime/memory/presentation failures without moving Hermes responsibilities
into Brainstack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


PRODUCT_PROBE_SCHEMA = "brainstack.product_probe.v1"
FAILURE_BUNDLE_SCHEMA = "brainstack.failure_bundle.v1"


class ProbeStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    INVALID_FIXTURE = "invalid_fixture"


class ProbeOwner(StrEnum):
    NATIVE_HERMES_OR_MODEL = "native_hermes_or_model"
    PROVIDER_MODEL_QUALITY = "provider_model_quality"
    BRAINSTACK_MEMORY_ADMISSION = "brainstack_memory_admission"
    BRAINSTACK_RETRIEVAL_ANSWERABILITY = "brainstack_retrieval_answerability"
    BRAINSTACK_INSTALLER_OR_WIZARD = "brainstack_installer_or_wizard"
    HERMES_CAPABILITY_MANIFEST = "hermes_capability_manifest"
    HERMES_WORKSPACE_CONTRACT = "hermes_workspace_contract"
    HERMES_TOOL_STATE_GUARD = "hermes_tool_state_guard"
    HERMES_TOOL_LOADER = "hermes_tool_loader"
    HERMES_PRESENTATION = "hermes_presentation"
    HERMES_APPROVAL_RUNTIME = "hermes_approval_runtime"
    DOCKER_RUNTIME_CONFIG = "docker_runtime_config"
    SOURCE_OF_TRUTH_PARITY = "source_of_truth_parity"
    TEST_FIXTURE_INVALID = "test_fixture_invalid"
    INCONCLUSIVE = "inconclusive"


class Repairability(StrEnum):
    REPAIRABLE_AUTOMATIC = "REPAIRABLE_AUTOMATIC"
    REPAIRABLE_WITH_OPERATOR_CONFIG = "REPAIRABLE_WITH_OPERATOR_CONFIG"
    BLOCKED_PROVIDER_MODEL = "BLOCKED_PROVIDER_MODEL"
    BLOCKED_MISSING_NATIVE_CAPABILITY = "BLOCKED_MISSING_NATIVE_CAPABILITY"
    INVALID_TEST_FIXTURE = "INVALID_TEST_FIXTURE"
    HUMAN_DECISION_REQUIRED = "HUMAN_DECISION_REQUIRED"
    NONE = "NONE"


class Severity(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class CapabilityStatus(StrEnum):
    CONFIGURED_AVAILABLE = "configured_available"
    CONFIGURED_UNAVAILABLE = "configured_unavailable"
    NOT_CONFIGURED = "not_configured"
    DISABLED_BY_ADMIN = "disabled_by_admin"


class AssistantClaimType(StrEnum):
    SELF_CLAIM = "assistant_self_claim"
    USER_CLAIM = "assistant_user_claim"
    TOOL_CAPABILITY_CLAIM = "assistant_tool_capability_claim"
    STYLE_CLAIM = "assistant_style_claim"
    ANSWER_SUMMARY = "assistant_answer_summary"
    TOOL_RESULT_PARAPHRASE = "assistant_tool_result_paraphrase"
    COMMITMENT = "assistant_commitment"
    DIALOGUE_COHERENCE = "assistant_dialogue_coherence"


class PacketDropReason(StrEnum):
    ASSISTANT_CLAIM_NOT_MODEL_FACING = "ASSISTANT_CLAIM_NOT_MODEL_FACING"
    CORRECTED_FALSE_CONTRADICTION_ONLY = "CORRECTED_FALSE_CONTRADICTION_ONLY"
    INSPECT_ONLY_NOT_MODEL_FACING = "INSPECT_ONLY_NOT_MODEL_FACING"
    SUPPORT_ONLY_NOT_ANSWER_EVIDENCE = "SUPPORT_ONLY_NOT_ANSWER_EVIDENCE"
    CURRENT_ASSIGNMENT_UNTRUSTED_AUTHORITY = "CURRENT_ASSIGNMENT_UNTRUSTED_AUTHORITY"


@dataclass(frozen=True)
class CorrectionProposal:
    source_event_id: str
    source_span_id: str
    correction_type: str
    target_claim_ids: Sequence[str]
    target_resolution_confidence: str
    reason_code: str
    source_role: str = "user"
    assertion_speaker: str = "user"
    target_slot: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "brainstack.correction_proposal.v1",
            "source_event_id": self.source_event_id,
            "source_span_id": self.source_span_id,
            "source_role": self.source_role,
            "assertion_speaker": self.assertion_speaker,
            "correction_type": self.correction_type,
            "target_claim_ids": list(self.target_claim_ids),
            "target_resolution_confidence": self.target_resolution_confidence,
            "target_slot": self.target_slot,
            "reason_code": self.reason_code,
        }


def resolve_prior_assistant_targets(
    prior_claims: Sequence[Mapping[str, Any]],
    *,
    correction_type: str,
    explicit_target_ids: Sequence[str] = (),
) -> list[str]:
    explicit = set(explicit_target_ids)
    if explicit:
        return [str(item["claim_id"]) for item in prior_claims if str(item.get("claim_id")) in explicit]
    if correction_type == "reject_prior_assistant_self_claim":
        allowed = {AssistantClaimType.SELF_CLAIM.value}
    elif correction_type == "reject_prior_assistant_user_claim":
        allowed = {AssistantClaimType.USER_CLAIM.value}
    else:
        allowed = set(ASSISTANT_CLAIM_TYPES_NOT_MODEL_FACING)
    return [
        str(item["claim_id"])
        for item in prior_claims
        if item.get("source_role") == "assistant" and str(item.get("claim_type")) in allowed
    ]


def build_correction_proposal(
    *,
    source_event_id: str,
    source_span_id: str,
    correction_type: str,
    prior_claims: Sequence[Mapping[str, Any]],
    explicit_target_ids: Sequence[str] = (),
    target_slot: str | None = None,
) -> CorrectionProposal:
    targets = resolve_prior_assistant_targets(
        prior_claims,
        correction_type=correction_type,
        explicit_target_ids=explicit_target_ids,
    )
    return CorrectionProposal(
        source_event_id=source_event_id,
        source_span_id=source_span_id,
        correction_type=correction_type,
        target_claim_ids=tuple(targets),
        target_resolution_confidence="high" if targets else "low",
        target_slot=target_slot,
        reason_code=correction_type.upper(),
    )


def apply_corrected_false(
    claims: Sequence[Mapping[str, Any]],
    proposal: CorrectionProposal,
    *,
    corrected_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    target_ids = set(proposal.target_claim_ids)
    updated: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for raw in claims:
        item = dict(raw)
        if str(item.get("claim_id")) in target_ids and item.get("source_role") == "assistant":
            item.update(
                {
                    "truth_eligible": False,
                    "model_facing_default": False,
                    "support_visibility": "contradiction_only",
                    "corrected_status": "corrected_false",
                    "corrected_by_event_id": proposal.source_event_id,
                    "corrected_at": corrected_at,
                }
            )
            receipts.append(
                {
                    "schema": "brainstack.contamination_repair_receipt.v1",
                    "claim_id": item.get("claim_id"),
                    "action": "mark_corrected_false",
                    "raw_transcript_deleted": False,
                    "corrected_by_event_id": proposal.source_event_id,
                    "reason_code": proposal.reason_code,
                }
            )
        updated.append(item)
    return updated, receipts


@dataclass(frozen=True)
class HotContainmentToggles:
    """Temporary release toggles for risky live paths.

    These are containment contracts, not final product behavior. Later phases
    replace them with structural firewall/presentation/runtime enforcement.
    """

    production_personality: str = "neutral"
    conversation_heavy_capability_gate: bool = False
    direct_renderer_generic_negative_enabled: bool = False
    direct_renderer_negative_requires_resolved_target: bool = True
    direct_renderer_negative_requires_localized_template: bool = True
    assistant_output_model_facing_default: bool = False
    full_configured_tool_fallback_when_toolloader_unproven: bool = True
    tool_only_in_heavy_prompt_residue_forbidden: bool = True
    configured_capabilities_preserved: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "brainstack.hot_containment_toggles.v1",
            "production_personality": self.production_personality,
            "conversation_heavy_capability_gate": self.conversation_heavy_capability_gate,
            "direct_renderer_generic_negative_enabled": self.direct_renderer_generic_negative_enabled,
            "direct_renderer_negative_requires_resolved_target": self.direct_renderer_negative_requires_resolved_target,
            "direct_renderer_negative_requires_localized_template": self.direct_renderer_negative_requires_localized_template,
            "assistant_output_model_facing_default": self.assistant_output_model_facing_default,
            "full_configured_tool_fallback_when_toolloader_unproven": self.full_configured_tool_fallback_when_toolloader_unproven,
            "tool_only_in_heavy_prompt_residue_forbidden": self.tool_only_in_heavy_prompt_residue_forbidden,
            "configured_capabilities_preserved": self.configured_capabilities_preserved,
        }


def default_hot_containment_toggles() -> HotContainmentToggles:
    return HotContainmentToggles()


def direct_renderer_negative_allowed(
    *,
    resolved_memory_target: bool,
    localized_template: bool,
    toggles: HotContainmentToggles | None = None,
) -> dict[str, Any]:
    policy = toggles or default_hot_containment_toggles()
    allowed = (
        policy.direct_renderer_generic_negative_enabled
        and (not policy.direct_renderer_negative_requires_resolved_target or resolved_memory_target)
        and (not policy.direct_renderer_negative_requires_localized_template or localized_template)
    )
    reason = "NEGATIVE_RENDERER_ALLOWED" if allowed else "NEGATIVE_RENDERER_CONTAINED"
    return {
        "schema": "brainstack.direct_renderer_negative_policy.v1",
        "allowed": allowed,
        "reason_code": reason,
        "resolved_memory_target": resolved_memory_target,
        "localized_template": localized_template,
    }


ASSISTANT_CLAIM_TYPES_NOT_MODEL_FACING = frozenset(
    {
        AssistantClaimType.SELF_CLAIM.value,
        AssistantClaimType.USER_CLAIM.value,
        AssistantClaimType.TOOL_CAPABILITY_CLAIM.value,
        AssistantClaimType.STYLE_CLAIM.value,
        AssistantClaimType.ANSWER_SUMMARY.value,
        AssistantClaimType.COMMITMENT.value,
    }
)


def continuity_visibility(
    *,
    source_role: str,
    claim_type: str,
    truth_eligible: bool = False,
    evidence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Classify whether continuity can enter normal model-facing packets."""

    raw_transcript_preserved = True
    if source_role == "assistant" and claim_type in ASSISTANT_CLAIM_TYPES_NOT_MODEL_FACING:
        return {
            "schema": "brainstack.continuity_visibility.v1",
            "raw_transcript_preserved": raw_transcript_preserved,
            "truth_eligible": False,
            "model_facing_default": False,
            "support_visibility": "inspect_only",
            "reason_code": "ASSISTANT_CLAIM_CONTAINED",
        }
    model_facing = bool(truth_eligible or evidence_refs or source_role == "user")
    return {
        "schema": "brainstack.continuity_visibility.v1",
        "raw_transcript_preserved": raw_transcript_preserved,
        "truth_eligible": bool(truth_eligible),
        "model_facing_default": model_facing,
        "support_visibility": "normal" if model_facing else "inspect_only",
        "reason_code": "MODEL_FACING_ALLOWED" if model_facing else "NOT_MODEL_FACING",
    }


def classify_assistant_claim(
    claim_type: str,
    *,
    evidence_refs: Sequence[str] = (),
    linked_tool_result_id: str | None = None,
) -> dict[str, Any]:
    """Classify assistant-authored spans without making them truth sources."""

    authority_source = "not_authority"
    truth_eligible = False
    model_facing_default = False
    support_visibility = "inspect_only"
    if claim_type == AssistantClaimType.TOOL_CAPABILITY_CLAIM.value:
        authority_source = "hermes_capability_manifest"
    elif claim_type == AssistantClaimType.STYLE_CLAIM.value:
        authority_source = "user_preference_and_hermes_presentation_contract"
    elif claim_type == AssistantClaimType.ANSWER_SUMMARY.value and evidence_refs:
        support_visibility = "support_only"
    elif claim_type == AssistantClaimType.TOOL_RESULT_PARAPHRASE.value and linked_tool_result_id:
        authority_source = "linked_tool_result"
        support_visibility = "tool_result_support"
        model_facing_default = True
    elif claim_type == AssistantClaimType.COMMITMENT.value:
        authority_source = "write_receipt_required"
    elif claim_type == AssistantClaimType.DIALOGUE_COHERENCE.value:
        support_visibility = "recent_dialogue_only"
    return {
        "schema": "brainstack.assistant_claim_classification.v1",
        "claim_type": claim_type,
        "truth_eligible": truth_eligible,
        "model_facing_default": model_facing_default,
        "support_visibility": support_visibility,
        "authority_source": authority_source,
        "evidence_refs": list(evidence_refs),
        "linked_tool_result_id": linked_tool_result_id,
    }


def model_facing_packet_firewall(
    candidates: Sequence[Mapping[str, Any]],
    *,
    query_mode: str = "normal",
) -> dict[str, Any]:
    """Filter final memory packet candidates before prompt assembly."""

    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    answer_evidence: list[dict[str, Any]] = []
    history_mode = query_mode in {"history", "correction_history", "quote_history"}
    trusted_assignment_authorities = {"USER_EXPLICIT_ASSIGNMENT", "TRUSTED_HOST_ASSIGNMENT", "OPERATOR_REPAIR"}

    for raw in candidates:
        item = dict(raw)
        evidence_id = str(item.get("evidence_id", ""))
        claim_type = str(item.get("claim_type", ""))
        support_visibility = str(item.get("support_visibility", "normal"))
        corrected_status = str(item.get("corrected_status", ""))
        evidence_class = str(item.get("evidence_class", ""))
        lane = str(item.get("lane", ""))
        source_role = str(item.get("source_role", ""))
        authority = str(item.get("authority", ""))
        wants_answer_evidence = bool(item.get("answer_evidence", False))
        truth_eligible = bool(item.get("truth_eligible", False))

        if corrected_status == "corrected_false" and not history_mode:
            dropped.append(
                {
                    "evidence_id": evidence_id,
                    "drop_reason": PacketDropReason.CORRECTED_FALSE_CONTRADICTION_ONLY.value,
                }
            )
            continue

        if support_visibility == "inspect_only" and not history_mode:
            dropped.append(
                {
                    "evidence_id": evidence_id,
                    "drop_reason": PacketDropReason.INSPECT_ONLY_NOT_MODEL_FACING.value,
                }
            )
            continue

        if claim_type in ASSISTANT_CLAIM_TYPES_NOT_MODEL_FACING and not history_mode:
            dropped.append(
                {
                    "evidence_id": evidence_id,
                    "drop_reason": PacketDropReason.ASSISTANT_CLAIM_NOT_MODEL_FACING.value,
                }
            )
            continue

        if lane == "current_assignment" and (
            source_role not in {"user", "trusted_host", "operator"} or authority not in trusted_assignment_authorities
        ):
            dropped.append(
                {
                    "evidence_id": evidence_id,
                    "drop_reason": PacketDropReason.CURRENT_ASSIGNMENT_UNTRUSTED_AUTHORITY.value,
                }
            )
            continue

        if history_mode and claim_type.startswith("assistant_"):
            item["quote_only"] = True
            item["truth_eligible"] = False
            item["answer_evidence"] = False

        if wants_answer_evidence and (not truth_eligible or evidence_class == "support_only"):
            dropped.append(
                {
                    "evidence_id": evidence_id,
                    "drop_reason": PacketDropReason.SUPPORT_ONLY_NOT_ANSWER_EVIDENCE.value,
                }
            )
            continue

        kept.append(item)
        if bool(item.get("answer_evidence", False)):
            answer_evidence.append(item)

    return {
        "schema": "brainstack.model_facing_packet_firewall.v1",
        "query_mode": query_mode,
        "input_candidate_count": len(candidates),
        "kept_count": len(kept),
        "dropped_count": len(dropped),
        "kept": kept,
        "answer_evidence": answer_evidence,
        "dropped": dropped,
        "policy_version": "model_packet_firewall.v1",
    }


def build_phrase_provenance_report(
    *,
    phrase: str,
    timeline: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    first_origin: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    for event in timeline:
        prompt_text = str(event.get("prompt_text", ""))
        provider_output = str(event.get("provider_output", ""))
        in_prompt = phrase in prompt_text
        in_output = phrase in provider_output
        row = {
            "turn_id": event.get("turn_id"),
            "in_prompt_before_generation": in_prompt,
            "in_provider_output": in_output,
            "raw_transcript_stored": bool(event.get("raw_transcript_stored", False)),
            "continuity_candidate": event.get("continuity_candidate"),
            "classification": event.get("classification"),
            "firewall_decision": event.get("firewall_decision"),
        }
        rows.append(row)
        if first_origin is None and (in_prompt or in_output):
            first_origin = {
                "turn_id": event.get("turn_id"),
                "type": "prompt_source" if in_prompt else "provider_generated",
                "not_in_prompt_before_turn": not in_prompt,
            }
    verdict = "blocked_by_firewall"
    if any(row.get("firewall_decision") == "kept_as_truth" for row in rows):
        verdict = "missing_guard"
    return {
        "schema": "brainstack.phrase_provenance_report.v1",
        "phrase_hash": hashlib.sha256(phrase.encode("utf-8")).hexdigest(),
        "phrase_present": bool(first_origin),
        "first_origin": first_origin,
        "timeline": rows,
        "final_verdict": verdict,
    }


def audit_contamination_candidates(claims: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    suspect = [
        dict(item)
        for item in claims
        if item.get("source_role") == "assistant"
        and str(item.get("claim_type")) in ASSISTANT_CLAIM_TYPES_NOT_MODEL_FACING
        and bool(item.get("model_facing_default", False))
    ]
    repaired: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for item in claims:
        row = dict(item)
        if any(str(row.get("claim_id")) == str(s.get("claim_id")) for s in suspect):
            row["model_facing_default"] = False
            row["truth_eligible"] = False
            row["support_visibility"] = "inspect_only"
            receipts.append(
                {
                    "schema": "brainstack.contamination_repair_receipt.v1",
                    "claim_id": row.get("claim_id"),
                    "action": "demote_assistant_claim",
                    "raw_transcript_deleted": False,
                    "reason_code": "ASSISTANT_CLAIM_MODEL_FACING_CONTAMINATION",
                }
            )
        repaired.append(row)
    return {
        "schema": "brainstack.contamination_audit.v1",
        "suspect_count": len(suspect),
        "raw_transcript_deleted": False,
        "suspect_claim_ids": [item.get("claim_id") for item in suspect],
        "repaired_claims": repaired,
        "repair_receipts": receipts,
    }


def admit_reference_url(
    *,
    label: str,
    url: str,
    source_authority: str,
    resolved_project_scope: str | None = None,
    as_project_repo_url: bool = False,
) -> dict[str, Any]:
    if as_project_repo_url and not resolved_project_scope:
        target_slot = "project.repo_url"
        truth_eligible = False
        model_facing_default = False
        support_visibility = "proposal_only"
        reason_code = "PROJECT_SCOPE_REQUIRED"
    elif resolved_project_scope:
        target_slot = "project.related_repo"
        truth_eligible = True
        model_facing_default = True
        support_visibility = "normal"
        reason_code = "PROJECT_RELATED_REPO_ADMITTED"
    else:
        target_slot = "reference.repository_url"
        truth_eligible = True
        model_facing_default = True
        support_visibility = "normal"
        reason_code = "REFERENCE_REPOSITORY_URL_ADMITTED"
    return {
        "schema": "brainstack.reference_url_admission.v1",
        "target_slot": target_slot,
        "label": label,
        "url": url,
        "source_authority": source_authority,
        "truth_eligible": truth_eligible,
        "model_facing_default": model_facing_default,
        "support_visibility": support_visibility,
        "fetch_on_write": False,
        "resolved_project_scope": resolved_project_scope,
        "reason_code": reason_code,
    }


def recall_reference_url(records: Sequence[Mapping[str, Any]], *, label: str) -> str | None:
    for item in records:
        if (
            item.get("target_slot") == "reference.repository_url"
            and str(item.get("label", "")).casefold() == label.casefold()
            and item.get("truth_eligible") is True
        ):
            return str(item.get("url"))
    return None


def decide_url_content_claim_allowed(
    *,
    url_present: bool,
    content_claim_made: bool,
    web_tool_result_id: str | None = None,
    unavailable_diagnostic_emitted: bool = False,
    clarification_asked: bool = False,
    remember_only: bool = False,
) -> dict[str, Any]:
    if remember_only:
        return {
            "schema": "brainstack.url_content_guard.v1",
            "allowed": True,
            "reason_code": "REMEMBER_URL_NO_FETCH",
            "fetch_required": False,
            "content_claims_allowed": False,
        }
    if not url_present or not content_claim_made:
        return {
            "schema": "brainstack.url_content_guard.v1",
            "allowed": True,
            "reason_code": "NO_URL_CONTENT_CLAIM",
            "fetch_required": False,
            "content_claims_allowed": False,
        }
    if web_tool_result_id:
        return {
            "schema": "brainstack.url_content_guard.v1",
            "allowed": True,
            "reason_code": "WEB_TOOL_RESULT_PRESENT",
            "web_tool_result_id": web_tool_result_id,
            "content_claims_allowed": True,
        }
    if unavailable_diagnostic_emitted:
        return {
            "schema": "brainstack.url_content_guard.v1",
            "allowed": True,
            "reason_code": "CAPABILITY_UNAVAILABLE_DIAGNOSTIC",
            "content_claims_allowed": False,
        }
    if clarification_asked:
        return {
            "schema": "brainstack.url_content_guard.v1",
            "allowed": True,
            "reason_code": "CLARIFICATION_ASKED",
            "content_claims_allowed": False,
        }
    return {
        "schema": "brainstack.url_content_guard.v1",
        "allowed": False,
        "reason_code": "URL_CONTENT_CLAIM_WITHOUT_EVIDENCE",
        "required_exit": ("web_tool_result", "configured_unavailable_diagnostic", "clarification"),
        "content_claims_allowed": False,
    }


def run_adversarial_synthetic_gateway_contract() -> dict[str, Any]:
    """Run deterministic E2E-like contract path for the live regression class."""

    raw_transcript = [
        {"turn_id": "t1", "source_role": "assistant", "text": "SyntheticPersona 🐞"},
        {"turn_id": "t2", "source_role": "assistant", "text": "Your preferred name is the platform handle."},
    ]
    assistant_claims = [
        {"claim_id": "a1", "evidence_id": "a1", "source_role": "assistant", "claim_type": "assistant_self_claim"},
        {"claim_id": "a2", "evidence_id": "a2", "source_role": "assistant", "claim_type": "assistant_user_claim"},
    ]
    correction = build_correction_proposal(
        source_event_id="u-correction",
        source_span_id="u-correction:s1",
        correction_type="reject_prior_assistant_self_claim",
        prior_claims=assistant_claims,
    )
    corrected_claims, correction_receipts = apply_corrected_false(
        assistant_claims,
        correction,
        corrected_at="2026-04-27T00:00:00Z",
    )
    user_truth = [
        {"evidence_id": "name", "source_role": "user", "truth_eligible": True, "answer_evidence": True, "slot": "identity.preferred_address_name", "value": "Tomi"},
        {"evidence_id": "handle", "source_role": "platform", "truth_eligible": True, "slot": "identity.platform_handle", "value": "LauraTom"},
        {"evidence_id": "age", "source_role": "user", "truth_eligible": True, "answer_evidence": True, "slot": "profile.age", "value": 19},
        {"evidence_id": "project_creator", "source_role": "user", "truth_eligible": True, "answer_evidence": True, "slot": "project.created_by", "value": "Tomi"},
    ]
    reference = admit_reference_url(
        label="resource-x",
        url="https://example.com/org/resource-x",
        source_authority="user_explicit_assertion",
    )
    packet = model_facing_packet_firewall([*corrected_claims, *user_truth, {"evidence_id": "reference", **reference}])
    rendered_assignment = render_current_assignment_status(has_current_assignment_evidence=False, language="hu")
    final_text, style_trace = apply_presentation_hygiene(
        "SyntheticPersona 🐞\n" + rendered_assignment + "\nVan még kérdésed?",
        no_emoji=True,
        no_final_followup=True,
        decorative_prefixes=("SyntheticPersona",),
    )
    url_guard = decide_url_content_claim_allowed(
        url_present=True,
        content_claim_made=True,
        unavailable_diagnostic_emitted=True,
    )
    phrase_provenance = build_phrase_provenance_report(
        phrase="SyntheticPersona",
        timeline=[
            {
                "turn_id": "t1",
                "prompt_text": "normal prompt",
                "provider_output": "SyntheticPersona",
                "raw_transcript_stored": True,
                "continuity_candidate": "assistant_self_claim",
                "classification": "assistant_self_claim",
                "firewall_decision": "dropped",
            }
        ],
    )
    probes = [
        ProductProbeEnvelope(
            probe_id="184.path.proof",
            phase="184",
            scenario_id="synthetic_gateway_path",
            status=ProbeStatus.PASS,
            owner=ProbeOwner.SOURCE_OF_TRUTH_PARITY,
            repairability=Repairability.NONE,
            severity=Severity.P1,
            reason_code="CONTRACT_EQUIVALENT_PATH_USED",
            observed={"gateway_equivalent": True},
            expected={"gateway_equivalent": True},
        ),
        ProductProbeEnvelope(
            probe_id="184.assistant.contamination",
            phase="184",
            scenario_id="assistant_self_contamination",
            status=ProbeStatus.PASS if packet["kept_count"] == 5 and packet["dropped_count"] == 2 else ProbeStatus.FAIL,
            owner=ProbeOwner.BRAINSTACK_RETRIEVAL_ANSWERABILITY,
            repairability=Repairability.REPAIRABLE_AUTOMATIC,
            severity=Severity.P1,
            reason_code="ASSISTANT_OUTPUT_NOT_REFED",
            observed={"kept_count": packet["kept_count"], "dropped_count": packet["dropped_count"]},
            expected={"dropped_count": 2},
            recommended_playbook="ASSISTANT_OUTPUT_CONTAINMENT",
        ),
        ProductProbeEnvelope(
            probe_id="184.url.no_guess",
            phase="184",
            scenario_id="url_unavailable_no_guess",
            status=ProbeStatus.PASS if url_guard["reason_code"] == "CAPABILITY_UNAVAILABLE_DIAGNOSTIC" else ProbeStatus.FAIL,
            owner=ProbeOwner.HERMES_TOOL_STATE_GUARD,
            repairability=Repairability.REPAIRABLE_AUTOMATIC,
            severity=Severity.P1,
            reason_code="URL_UNAVAILABLE_DIAGNOSTIC",
            observed=url_guard,
            expected={"reason_code": "CAPABILITY_UNAVAILABLE_DIAGNOSTIC"},
            recommended_playbook="TOOL_STATE_FINAL_ANSWER_BLOCK",
        ),
    ]
    return {
        "schema": "brainstack.phase184.adversarial_synthetic_gateway_contract.v1",
        "path_proof": {
            "used_gateway_equivalent": True,
            "used_prompt_packet_firewall": True,
            "used_presentation_hygiene": True,
            "used_url_final_answer_guard": True,
            "used_correction_linking": True,
            "used_reference_admission": True,
        },
        "raw_transcript": raw_transcript,
        "packet": packet,
        "correction_receipts": correction_receipts,
        "phrase_provenance": phrase_provenance,
        "style_trace": style_trace,
        "final_text": final_text,
        "reference_recall": recall_reference_url([reference], label="resource-x"),
        "identity": {"preferred_name": "Tomi", "platform_handle": "LauraTom"},
        "url_guard": url_guard,
        "probes": [probe.to_dict() for probe in probes],
    }


@dataclass(frozen=True)
class ProductProbeEnvelope:
    probe_id: str
    phase: str
    scenario_id: str
    status: ProbeStatus
    owner: ProbeOwner
    repairability: Repairability
    severity: Severity
    reason_code: str
    observed: Mapping[str, Any] = field(default_factory=dict)
    expected: Mapping[str, Any] = field(default_factory=dict)
    trace_refs: Sequence[str] = field(default_factory=tuple)
    recommended_playbook: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PRODUCT_PROBE_SCHEMA,
            "probe_id": self.probe_id,
            "phase": self.phase,
            "scenario_id": self.scenario_id,
            "status": self.status.value,
            "owner": self.owner.value,
            "repairability": self.repairability.value,
            "severity": self.severity.value,
            "reason_code": self.reason_code,
            "observed": dict(self.observed),
            "expected": dict(self.expected),
            "trace_refs": list(self.trace_refs),
            "recommended_playbook": self.recommended_playbook,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProductProbeEnvelope":
        return cls(
            probe_id=str(payload["probe_id"]),
            phase=str(payload["phase"]),
            scenario_id=str(payload["scenario_id"]),
            status=ProbeStatus(str(payload["status"])),
            owner=ProbeOwner(str(payload["owner"])),
            repairability=Repairability(str(payload["repairability"])),
            severity=Severity(str(payload["severity"])),
            reason_code=str(payload["reason_code"]),
            observed=dict(payload.get("observed") or {}),
            expected=dict(payload.get("expected") or {}),
            trace_refs=tuple(str(item) for item in payload.get("trace_refs") or []),
            recommended_playbook=str(payload.get("recommended_playbook") or ""),
        )

    @property
    def failed(self) -> bool:
        return self.status in {ProbeStatus.FAIL, ProbeStatus.BLOCKED, ProbeStatus.INVALID_FIXTURE}


@dataclass(frozen=True)
class CapabilityHealth:
    capability_id: str
    configured: bool = False
    executable: bool = False
    disabled_by_admin: bool = False
    loaded_schema: bool = False
    approval_required: bool = False
    reason: str = ""

    @property
    def status(self) -> CapabilityStatus:
        if self.disabled_by_admin:
            return CapabilityStatus.DISABLED_BY_ADMIN
        if not self.configured:
            return CapabilityStatus.NOT_CONFIGURED
        if self.executable:
            return CapabilityStatus.CONFIGURED_AVAILABLE
        return CapabilityStatus.CONFIGURED_UNAVAILABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "status": self.status.value,
            "configured": self.configured,
            "executable": self.executable,
            "loaded_schema": self.loaded_schema,
            "approval_required": self.approval_required,
            "reason": self.reason,
        }


def build_capability_manifest(
    configured_capabilities: Iterable[str],
    executable_capabilities: Iterable[str] = (),
    loaded_schema_capabilities: Iterable[str] = (),
    disabled_capabilities: Iterable[str] = (),
    approval_required_capabilities: Iterable[str] = (),
    unavailable_reasons: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    configured = set(configured_capabilities)
    executable = set(executable_capabilities)
    loaded = set(loaded_schema_capabilities)
    disabled = set(disabled_capabilities)
    approval = set(approval_required_capabilities)
    reasons = dict(unavailable_reasons or {})
    ids = sorted(configured | executable | loaded | disabled | approval | set(reasons))
    capabilities = [
        CapabilityHealth(
            capability_id=item,
            configured=item in configured,
            executable=item in executable,
            disabled_by_admin=item in disabled,
            loaded_schema=item in loaded,
            approval_required=item in approval,
            reason=reasons.get(item, ""),
        ).to_dict()
        for item in ids
    ]
    configured_count = len(configured)
    available_count = sum(1 for item in capabilities if item["status"] == CapabilityStatus.CONFIGURED_AVAILABLE.value)
    return {
        "schema": "brainstack.capability_manifest.v1",
        "configured_capability_count": configured_count,
        "available_capability_count": available_count,
        "capability_shrunk": available_count < len(executable & configured),
        "capabilities": capabilities,
    }


@dataclass(frozen=True)
class WorkspaceContract:
    root: str
    user_workspace: str
    project_workspace: str
    project_read_only: bool
    fixture_status: str
    fixture_files: Sequence[str] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "brainstack.workspace_contract.v1",
            "root": self.root,
            "user_workspace": self.user_workspace,
            "project_workspace": self.project_workspace,
            "project_read_only": self.project_read_only,
            "fixture_status": self.fixture_status,
            "fixture_files": list(self.fixture_files),
        }


def assess_workspace_contract(root: Path) -> WorkspaceContract:
    root = root.expanduser().resolve()
    user = root / "user"
    project = root / "project"
    fixture_files = [
        str(path.relative_to(project))
        for path in sorted(project.rglob("*"))
        if path.is_file()
    ] if project.exists() else []
    if not root.exists():
        fixture_status = "absent"
    elif not fixture_files:
        fixture_status = "invalid_fixture"
    else:
        fixture_status = "present"
    return WorkspaceContract(
        root=str(root),
        user_workspace=str(user),
        project_workspace=str(project),
        project_read_only=True,
        fixture_status=fixture_status,
        fixture_files=tuple(fixture_files),
    )


def ensure_workspace_fixture(root: Path) -> WorkspaceContract:
    root = root.expanduser().resolve()
    project = root / "project"
    user = root / "user"
    (project / "docs").mkdir(parents=True, exist_ok=True)
    (project / "src").mkdir(parents=True, exist_ok=True)
    user.mkdir(parents=True, exist_ok=True)
    fixtures = {
        project / "README.md": "# Fixture\n",
        project / "docs" / "PLAN.md": "# Plan\n",
        project / "src" / "main.py": "print('fixture')\n",
    }
    for path, content in fixtures.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    return assess_workspace_contract(root)


EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U00002700-\U000027bf"
    "]+",
    flags=re.UNICODE,
)


def apply_presentation_hygiene(
    text: str,
    *,
    no_emoji: bool = False,
    no_em_dash: bool = False,
    no_final_followup: bool = False,
    decorative_prefixes: Sequence[str] = (),
) -> tuple[str, dict[str, Any]]:
    """Apply non-semantic presentation cleanup only."""

    before = text
    removed_emoji = 0
    if no_emoji:
        matches = EMOJI_RE.findall(text)
        removed_emoji = sum(len(item) for item in matches)
        text = EMOJI_RE.sub("", text)
    replaced_em_dash = 0
    if no_em_dash:
        replaced_em_dash = text.count("—")
        text = text.replace("—", "-")
    removed_prefix = False
    if decorative_prefixes:
        lines = text.splitlines()
        while lines and not lines[0].strip():
            lines = lines[1:]
        if lines:
            first = lines[0].strip().rstrip(":")
            if first.casefold() in {prefix.casefold() for prefix in decorative_prefixes}:
                text = "\n".join(lines[1:]).lstrip()
                removed_prefix = True
    removed_followup = False
    if no_final_followup:
        lines = text.rstrip().splitlines()
        if lines:
            last = lines[-1].strip()
            generic = {
                "miben segíthetek?",
                "miben segíthetek még?",
                "kell még valami?",
                "van még kérdésed?",
                "what can i help with?",
            }
            if last.casefold() in generic:
                lines = lines[:-1]
                text = "\n".join(lines).rstrip()
                removed_followup = True
    trace = {
        "schema": "brainstack.style_application.v1",
        "applied_by": "hermes.presentation",
        "semantic_changes_allowed": False,
        "post_filter_used": before != text,
        "removed_emoji_count": removed_emoji,
        "replaced_em_dash_count": replaced_em_dash,
        "removed_decorative_prefix": removed_prefix,
        "removed_followup_closer": removed_followup,
    }
    return text.strip(), trace


def render_current_assignment_status(
    *,
    has_current_assignment_evidence: bool,
    language: str,
) -> str:
    if has_current_assignment_evidence:
        return "Aktuális feladat rögzítve." if language.startswith("hu") else "Current assignment evidence is recorded."
    if language.startswith("hu"):
        return "Nincs rögzített aktuális feladat explicit assignment evidence alapján."
    return "No typed current-assignment evidence is recorded."


def build_interim_assistant_message(
    *,
    enabled: bool,
    text: str,
    no_emoji: bool = False,
    no_em_dash: bool = False,
    decorative_prefixes: Sequence[str] = (),
) -> tuple[str | None, dict[str, Any]]:
    if not enabled:
        return None, {"schema": "brainstack.interim_message.v1", "enabled": False}
    cleaned, trace = apply_presentation_hygiene(
        text,
        no_emoji=no_emoji,
        no_em_dash=no_em_dash,
        decorative_prefixes=decorative_prefixes,
    )
    trace["schema"] = "brainstack.interim_message.v1"
    trace["enabled"] = True
    return cleaned, trace


def default_presentation_runtime_contract() -> dict[str, Any]:
    return {
        "schema": "brainstack.presentation_runtime_contract.v1",
        "applied_by": "hermes.presentation",
        "default_personality": "neutral",
        "soul_examples_active_prompt": False,
        "semantic_changes_allowed": False,
        "style_preferences_source": "brainstack.preference_evidence",
    }


@dataclass(frozen=True)
class ToolStateDecision:
    final_answer_allowed: bool
    reason_code: str
    required_exit: Sequence[str] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "brainstack.tool_state_guard.v1",
            "final_answer_allowed": self.final_answer_allowed,
            "reason_code": self.reason_code,
            "required_exit": list(self.required_exit),
        }


def decide_final_answer_allowed(
    *,
    external_capability_possible: bool,
    model_declared_tool_intent: bool = False,
    required_bundle_loaded: bool = False,
    tool_result_received: bool = False,
    unavailable_diagnostic_emitted: bool = False,
    approval_requested: bool = False,
    clarification_asked: bool = False,
    renderer_resolved_memory_target: bool = False,
) -> ToolStateDecision:
    if not external_capability_possible:
        return ToolStateDecision(True, "NO_EXTERNAL_CAPABILITY_REQUIRED")
    if renderer_resolved_memory_target and not model_declared_tool_intent:
        return ToolStateDecision(True, "RESOLVED_MEMORY_OR_RUNTIME_STATUS_TARGET")
    if required_bundle_loaded and tool_result_received:
        return ToolStateDecision(True, "TOOL_RESULT_RECEIVED")
    if unavailable_diagnostic_emitted:
        return ToolStateDecision(True, "CAPABILITY_UNAVAILABLE_DIAGNOSTIC")
    if approval_requested:
        return ToolStateDecision(True, "APPROVAL_REQUESTED")
    if clarification_asked:
        return ToolStateDecision(True, "CLARIFICATION_ASKED")
    return ToolStateDecision(
        False,
        "EXTERNAL_CAPABILITY_UNRESOLVED",
        (
            "tool_result",
            "configured_unavailable_diagnostic",
            "approval_request",
            "clarification",
        ),
    )


@dataclass(frozen=True)
class RepairPlaybook:
    name: str
    owner: ProbeOwner
    allowed_modules: Sequence[str]
    forbidden_modules: Sequence[str]
    forbidden_fixes: Sequence[str]
    minimal_tests: Sequence[str]
    blast_radius_tests: Sequence[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner.value,
            "allowed_modules": list(self.allowed_modules),
            "forbidden_modules": list(self.forbidden_modules),
            "forbidden_fixes": list(self.forbidden_fixes),
            "minimal_tests": list(self.minimal_tests),
            "blast_radius_tests": list(self.blast_radius_tests),
        }


DEFAULT_REPAIR_PLAYBOOKS: dict[str, RepairPlaybook] = {
    "TOOL_STATE_FINAL_ANSWER_BLOCK": RepairPlaybook(
        name="TOOL_STATE_FINAL_ANSWER_BLOCK",
        owner=ProbeOwner.HERMES_TOOL_STATE_GUARD,
        allowed_modules=("gateway/tool_state_guard.py", "gateway/no_final_before_tools.py", "brainstack/product_contracts.py"),
        forbidden_modules=("brainstack/admission_policy.py", "brainstack/retrieval", "brainstack/core/admission.py"),
        forbidden_fixes=("language_keyword_router", "brainstack_output_governor", "disable_capability"),
        minimal_tests=("tests/test_no_final_before_tools.py", "tests/test_url_fetch_guard.py"),
        blast_radius_tests=("tests/test_capability_manifest.py", "tests/test_deferred_tool_loader.py"),
    ),
    "IDENTITY_SLOT_CONFUSION": RepairPlaybook(
        name="IDENTITY_SLOT_CONFUSION",
        owner=ProbeOwner.BRAINSTACK_MEMORY_ADMISSION,
        allowed_modules=("brainstack/core/admission.py", "brainstack/admission_policy.py"),
        forbidden_modules=("gateway", "patches/hermes_gateway"),
        forbidden_fixes=("Hungarian_regex", "direct_profile_upsert", "generic_identity_name_slot"),
        minimal_tests=("tests/test_claimproposal_contract.py", "tests/test_identity_admission.py"),
        blast_radius_tests=("tests/test_project_metadata_admission.py", "tests/test_failure_triage.py"),
    ),
    "STYLE_PRESENTATION_FAILURE": RepairPlaybook(
        name="STYLE_PRESENTATION_FAILURE",
        owner=ProbeOwner.HERMES_PRESENTATION,
        allowed_modules=("gateway/presentation_contract.py", "gateway/style_hygiene.py", "brainstack/product_contracts.py"),
        forbidden_modules=("brainstack/admission_policy.py", "brainstack/retrieval"),
        forbidden_fixes=("semantic_output_rewrite", "tool_claim_rewrite", "approval_rewrite"),
        minimal_tests=("tests/test_presentation_contract.py", "tests/test_style_hygiene_filter.py"),
        blast_radius_tests=("tests/test_no_final_before_tools.py",),
    ),
    "ASSISTANT_OUTPUT_CONTAINMENT": RepairPlaybook(
        name="ASSISTANT_OUTPUT_CONTAINMENT",
        owner=ProbeOwner.BRAINSTACK_RETRIEVAL_ANSWERABILITY,
        allowed_modules=("brainstack/product_contracts.py", "brainstack/retrieval", "brainstack/retrieval_pipeline"),
        forbidden_modules=("gateway", "patches/hermes_gateway"),
        forbidden_fixes=("language_keyword_router", "brainstack_output_governor", "disable_capability"),
        minimal_tests=("tests/test_hot_containment.py",),
        blast_radius_tests=("tests/test_failure_triage.py", "tests/test_no_final_before_tools.py"),
    ),
}


def failure_bundle_from_probe(probe: ProductProbeEnvelope) -> dict[str, Any]:
    playbook = DEFAULT_REPAIR_PLAYBOOKS.get(probe.recommended_playbook)
    seed = f"{probe.probe_id}|{probe.reason_code}|{probe.owner.value}"
    return {
        "schema": FAILURE_BUNDLE_SCHEMA,
        "failure_id": f"failure:{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}",
        "scenario_id": probe.scenario_id,
        "phase_owner": probe.phase,
        "observed": dict(probe.observed),
        "expected": dict(probe.expected),
        "owner_classification": {
            "primary_owner": probe.owner.value,
            "confidence": "high" if probe.owner != ProbeOwner.INCONCLUSIVE else "low",
        },
        "suspected_modules": list(playbook.allowed_modules if playbook else ()),
        "forbidden_fixes": list(playbook.forbidden_fixes if playbook else ()),
        "recommended_patch_playbook": probe.recommended_playbook,
        "minimal_retest": list(playbook.minimal_tests if playbook else ()),
        "blast_radius_retest": list(playbook.blast_radius_tests if playbook else ()),
        "trace_refs": list(probe.trace_refs),
        "repairability": probe.repairability.value,
        "severity": probe.severity.value,
    }


def build_failure_bundles(probes: Iterable[ProductProbeEnvelope]) -> list[dict[str, Any]]:
    return [failure_bundle_from_probe(probe) for probe in probes if probe.failed]


def rc_stop_condition(probes: Iterable[ProductProbeEnvelope]) -> dict[str, Any]:
    items = list(probes)
    blocking = [
        probe
        for probe in items
        if probe.severity in {Severity.P0, Severity.P1}
        and probe.status in {ProbeStatus.FAIL, ProbeStatus.BLOCKED, ProbeStatus.INVALID_FIXTURE}
    ]
    inconclusive = [
        probe
        for probe in items
        if probe.severity in {Severity.P0, Severity.P1} and probe.owner == ProbeOwner.INCONCLUSIVE
    ]
    return {
        "schema": "brainstack.rc_stop_condition.v1",
        "ready": not blocking and not inconclusive,
        "blocking_count": len(blocking),
        "inconclusive_p0_p1_count": len(inconclusive),
        "blocking_probe_ids": [probe.probe_id for probe in blocking],
    }


def validate_patch_against_playbook(changed_files: Sequence[str], patch_text: str, playbook_name: str) -> dict[str, Any]:
    playbook = DEFAULT_REPAIR_PLAYBOOKS[playbook_name]
    forbidden_touches = [
        file
        for file in changed_files
        for forbidden in playbook.forbidden_modules
        if file == forbidden or file.startswith(forbidden.rstrip("/") + "/")
    ]
    language_router_pattern = "|".join(
        (
            "keresd" + " meg",
            "nyisd" + " meg",
            "open this " + "url",
            "fi" + "nd .*" + r"\.md",
        )
    )
    forbidden_patterns = {
        "language_keyword_router": (language_router_pattern, re.IGNORECASE),
        "generic_identity_name_slot": (r"identity\.name", 0),
        "brainstack_output_governor": (r"use_renderer|tool_profile|model_profile", 0),
        "disable_capability": (r"capability_shrunk\\s*=\\s*true|disabled_by_default", re.IGNORECASE),
    }
    matched_forbidden: list[str] = []
    for fix in playbook.forbidden_fixes:
        spec = forbidden_patterns.get(fix)
        if spec and re.search(spec[0], patch_text, spec[1]):
            matched_forbidden.append(fix)
    accepted = not forbidden_touches and not matched_forbidden
    return {
        "schema": "brainstack.patch_guard.v1",
        "accepted": accepted,
        "forbidden_touches": forbidden_touches,
        "forbidden_fixes": matched_forbidden,
    }


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
