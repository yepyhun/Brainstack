"""Policy for derived claim -> durable truth projection admission."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from .core.admission import (
    ADMISSION_POLICY_VERSION,
    AdmissionDecision,
    AdmissionDecisionType,
    AssertionSpeaker,
    ClaimProposal,
    SLOT_REGISTRY_VERSION,
    SlotSpec,
    SourceAuthority,
    SpanKind,
    SupportVisibility,
)


REASON_ADMISSION_ACCEPTED = "ADMISSION_ACCEPTED"
REASON_ADMISSION_SUPERSESSION = "ADMISSION_SUPERSESSION"
REASON_GENERIC_IDENTITY_NAME_REJECTED = "GENERIC_IDENTITY_NAME_REJECTED"
REASON_RUNTIME_CAPABILITY_NOT_MEMORY_TRUTH = "RUNTIME_CAPABILITY_NOT_MEMORY_TRUTH"
REASON_ASSISTANT_CLAIM_NOT_USER_TRUTH = "ASSISTANT_CLAIM_NOT_USER_TRUTH"
REASON_UNKNOWN_DERIVED_GRAPH_SLOT = "UNKNOWN_DERIVED_GRAPH_SLOT"
REASON_UNSUPPORTED_AUTHORITY = "UNSUPPORTED_ADMISSION_AUTHORITY"
REASON_MISSING_VALUE = "MISSING_CANDIDATE_VALUE"
VERIFIED_USER_SPAN_PROOF_KEY = "verified_user_span_proof"

TRUSTED_AUTHORITIES = frozenset(
    {
        SourceAuthority.USER_EXPLICIT_ASSERTION,
        SourceAuthority.USER_CORRECTION,
        SourceAuthority.TRUSTED_HOST,
        SourceAuthority.TRUSTED_IMPORT,
    }
)

SLOT_REGISTRY: dict[str, SlotSpec] = {
    "identity.platform_handle": SlotSpec(
        slot_id="identity.platform_handle",
        shelf="profile",
        storage_key="identity:platform_handle",
        exclusive_current=True,
        allowed_authorities=frozenset({SourceAuthority.TRUSTED_HOST, SourceAuthority.USER_EXPLICIT_ASSERTION}),
    ),
    "identity.platform_display_name": SlotSpec(
        slot_id="identity.platform_display_name",
        shelf="profile",
        storage_key="identity:platform_display_name",
        exclusive_current=True,
        allowed_authorities=frozenset({SourceAuthority.TRUSTED_HOST, SourceAuthority.USER_EXPLICIT_ASSERTION}),
    ),
    "identity.preferred_address_name": SlotSpec(
        slot_id="identity.preferred_address_name",
        shelf="profile",
        storage_key="identity:preferred_address_name",
        exclusive_current=True,
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "identity.legal_name": SlotSpec(
        slot_id="identity.legal_name",
        shelf="profile",
        storage_key="identity:legal_name",
        exclusive_current=True,
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "identity.age": SlotSpec(
        slot_id="identity.age",
        shelf="profile",
        storage_key="identity:age",
        exclusive_current=True,
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "preference.addressing": SlotSpec(
        slot_id="preference.addressing",
        shelf="profile",
        storage_key="preference:addressing",
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "preference.assistant_address_name": SlotSpec(
        slot_id="preference.assistant_address_name",
        shelf="profile",
        storage_key="preference:assistant_address_name",
        exclusive_current=True,
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "preference.communication_style": SlotSpec(
        slot_id="preference.communication_style",
        shelf="profile",
        storage_key="preference:communication_style",
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "preference.formatting": SlotSpec(
        slot_id="preference.formatting",
        shelf="profile",
        storage_key="preference:formatting",
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "preference.verbosity": SlotSpec(
        slot_id="preference.verbosity",
        shelf="profile",
        storage_key="preference:verbosity",
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "preference.style_contract": SlotSpec(
        slot_id="preference.style_contract",
        shelf="profile",
        storage_key="preference:style_contract",
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "preference.diagnostics": SlotSpec(
        slot_id="preference.diagnostics",
        shelf="profile",
        storage_key="preference:diagnostics",
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "reference.repository_url": SlotSpec(
        slot_id="reference.repository_url",
        shelf="profile",
        storage_key="reference:repository_url",
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "project.created_by": SlotSpec(
        slot_id="project.created_by",
        shelf="graph",
        storage_key="project:created_by",
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "project.maintained_by": SlotSpec(
        slot_id="project.maintained_by",
        shelf="graph",
        storage_key="project:maintained_by",
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "project.inspired_by": SlotSpec(
        slot_id="project.inspired_by",
        shelf="graph",
        storage_key="project:inspired_by",
        allowed_authorities=TRUSTED_AUTHORITIES,
        default_support_visibility=SupportVisibility.NORMAL,
    ),
    "project.component_inspired_by": SlotSpec(
        slot_id="project.component_inspired_by",
        shelf="graph",
        storage_key="project:component_inspired_by",
        allowed_authorities=TRUSTED_AUTHORITIES,
        default_support_visibility=SupportVisibility.NORMAL,
    ),
    "project.repo_url": SlotSpec(
        slot_id="project.repo_url",
        shelf="graph",
        storage_key="project:repo_url",
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "project.homepage_url": SlotSpec(
        slot_id="project.homepage_url",
        shelf="graph",
        storage_key="project:homepage_url",
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "project.related_repo": SlotSpec(
        slot_id="project.related_repo",
        shelf="graph",
        storage_key="project:related_repo",
        allowed_authorities=TRUSTED_AUTHORITIES,
    ),
    "project.donor_source": SlotSpec(
        slot_id="project.donor_source",
        shelf="graph",
        storage_key="project:donor_source",
        allowed_authorities=TRUSTED_AUTHORITIES,
        default_support_visibility=SupportVisibility.NORMAL,
    ),
    "project.component_role": SlotSpec(
        slot_id="project.component_role",
        shelf="graph",
        storage_key="project:component_role",
        allowed_authorities=TRUSTED_AUTHORITIES,
        default_support_visibility=SupportVisibility.NORMAL,
    ),
    "runtime.capability_snapshot_ref": SlotSpec(
        slot_id="runtime.capability_snapshot_ref",
        shelf="runtime",
        storage_key="runtime:capability_snapshot_ref",
        allowed_authorities=frozenset({SourceAuthority.TRUSTED_RUNTIME}),
        supporting_authorities=frozenset({SourceAuthority.RUNTIME_DIAGNOSTIC}),
        default_support_visibility=SupportVisibility.INSPECT_ONLY,
    ),
}

PROFILE_SLOT_ALIASES = {
    "identity:platform_handle": "identity.platform_handle",
    "identity:platform_display_name": "identity.platform_display_name",
    "identity:preferred_address_name": "identity.preferred_address_name",
    "identity:preferred_name": "identity.preferred_address_name",
    "identity:user_name": "identity.preferred_address_name",
    "identity:legal_name": "identity.legal_name",
    "identity:age": "identity.age",
    "reference:repository_url": "reference.repository_url",
    "preference:addressing": "preference.addressing",
    "preference:assistant_address_name": "preference.assistant_address_name",
    "preference:assistant_name": "preference.assistant_address_name",
    "preference:bot_address_name": "preference.assistant_address_name",
    "preference:communication_style": "preference.communication_style",
    "preference:formatting": "preference.formatting",
    "preference:verbosity": "preference.verbosity",
    "preference:style_contract": "preference.style_contract",
    "preference:diagnostics": "preference.diagnostics",
}

GRAPH_RELATION_ALIASES = {
    "created_by": "project.created_by",
    "creator_of": "project.created_by",
    "project.created_by": "project.created_by",
    "maintained_by": "project.maintained_by",
    "project.maintained_by": "project.maintained_by",
    "inspired_by": "project.inspired_by",
    "inspiration": "project.inspired_by",
    "project.inspired_by": "project.inspired_by",
    "component_inspired_by": "project.component_inspired_by",
    "project.component_inspired_by": "project.component_inspired_by",
    "repo_url": "project.repo_url",
    "repository_url": "project.repo_url",
    "project.repo_url": "project.repo_url",
    "homepage_url": "project.homepage_url",
    "project.homepage_url": "project.homepage_url",
    "related_repo": "project.related_repo",
    "project.related_repo": "project.related_repo",
    "donor_source": "project.donor_source",
    "project.donor_source": "project.donor_source",
    "component_role": "project.component_role",
    "project.component_role": "project.component_role",
}

CAPABILITY_SLOTS = frozenset(
    {
        "assistant.has_shell_access",
        "assistant.has_terminal_access",
        "assistant.has_tool_access",
        "assistant.can_execute_terminal",
        "runtime.shell_access",
        "runtime.terminal_access",
        "runtime.tool_access",
    }
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _lower(value: Any) -> str:
    return _text(value).casefold()


def _hash_text(value: Any) -> str:
    return hashlib.sha256(_text(value).encode("utf-8")).hexdigest()


def _enum_value(enum_cls: type[Any], value: Any, default: Any) -> Any:
    normalized = _lower(value)
    for item in enum_cls:
        if normalized == str(item.value).casefold():
            return item
    return default


def _metadata(candidate: Mapping[str, Any], base_metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(base_metadata or {})
    if payload.pop("_candidate_metadata_sanitized", None):
        return payload
    raw = candidate.get("metadata")
    if isinstance(raw, Mapping):
        payload.update(raw)
    provenance = candidate.get("provenance")
    if isinstance(provenance, Mapping):
        nested = dict(payload.get("provenance") or {})
        nested.update(provenance)
        payload["provenance"] = nested
    return payload


def _first_metadata_text(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _text(payload.get(key))
        if value:
            return value
    provenance = payload.get("provenance")
    if isinstance(provenance, Mapping):
        for key in keys:
            value = _text(provenance.get(key))
            if value:
                return value
    return ""


def _authority_from_payload(payload: Mapping[str, Any], *, source: str) -> SourceAuthority:
    source_text = _lower(source)
    explicit = _first_metadata_text(payload, ("authority_class", "source_authority", "authority"))
    explicit_authority = _enum_value(SourceAuthority, explicit, SourceAuthority.UNKNOWN) if explicit else SourceAuthority.UNKNOWN
    speaker = _enum_value(
        AssertionSpeaker,
        _first_metadata_text(payload, ("assertion_speaker", "speaker", "source_role", "role")),
        AssertionSpeaker.UNKNOWN,
    )
    span_kind = _enum_value(SpanKind, _first_metadata_text(payload, ("span_kind", "kind")), SpanKind.UNKNOWN)
    if source_text.startswith("tier2:") or source_text.startswith("consolidation:"):
        if speaker in {AssertionSpeaker.ASSISTANT, AssertionSpeaker.QUOTED_ASSISTANT} or explicit_authority in {
            SourceAuthority.ASSISTANT_CLAIM,
            SourceAuthority.ASSISTANT_SELF_CLAIM,
        }:
            return SourceAuthority.ASSISTANT_CLAIM
        if span_kind == SpanKind.RUNTIME_DIAGNOSTIC or speaker == AssertionSpeaker.RUNTIME:
            return SourceAuthority.RUNTIME_DIAGNOSTIC
        proof = payload.get(VERIFIED_USER_SPAN_PROOF_KEY)
        if isinstance(proof, Mapping) and str(proof.get("status") or "") == "verified":
            return SourceAuthority.USER_EXPLICIT_ASSERTION
        return SourceAuthority.TIER2_SUMMARY
    if explicit_authority != SourceAuthority.UNKNOWN:
        return explicit_authority
    if speaker in {AssertionSpeaker.ASSISTANT, AssertionSpeaker.QUOTED_ASSISTANT}:
        return SourceAuthority.ASSISTANT_CLAIM
    if span_kind == SpanKind.RUNTIME_DIAGNOSTIC or speaker == AssertionSpeaker.RUNTIME:
        return SourceAuthority.RUNTIME_DIAGNOSTIC
    if speaker in {AssertionSpeaker.TRUSTED_HOST, AssertionSpeaker.TRUSTED_IMPORT}:
        return SourceAuthority.TRUSTED_HOST
    if speaker == AssertionSpeaker.USER or source_text.startswith("user"):
        return SourceAuthority.USER_CORRECTION if span_kind == SpanKind.CORRECTION else SourceAuthority.USER_EXPLICIT_ASSERTION
    if source_text.startswith("session_recap:"):
        return SourceAuthority.SESSION_RECAP
    if source_text.startswith("pulse:") or source_text.startswith("background:"):
        return SourceAuthority.PULSE_BACKGROUND
    return SourceAuthority.UNKNOWN


def _speaker_from_payload(payload: Mapping[str, Any], authority: SourceAuthority) -> AssertionSpeaker:
    speaker = _enum_value(
        AssertionSpeaker,
        _first_metadata_text(payload, ("assertion_speaker", "speaker", "source_role", "role")),
        AssertionSpeaker.UNKNOWN,
    )
    if authority == SourceAuthority.TIER2_SUMMARY and speaker == AssertionSpeaker.USER:
        return AssertionSpeaker.UNKNOWN
    if speaker != AssertionSpeaker.UNKNOWN:
        return speaker
    if authority in {SourceAuthority.USER_EXPLICIT_ASSERTION, SourceAuthority.USER_CORRECTION}:
        return AssertionSpeaker.USER
    if authority == SourceAuthority.RUNTIME_DIAGNOSTIC:
        return AssertionSpeaker.RUNTIME
    if authority == SourceAuthority.ASSISTANT_CLAIM:
        return AssertionSpeaker.ASSISTANT
    if authority in {SourceAuthority.TRUSTED_HOST, SourceAuthority.TRUSTED_IMPORT}:
        return AssertionSpeaker.TRUSTED_HOST
    return AssertionSpeaker.UNKNOWN


def _span_kind_from_payload(payload: Mapping[str, Any], authority: SourceAuthority) -> SpanKind:
    span_kind = _enum_value(SpanKind, _first_metadata_text(payload, ("span_kind", "kind")), SpanKind.UNKNOWN)
    if span_kind != SpanKind.UNKNOWN:
        return span_kind
    if authority == SourceAuthority.USER_CORRECTION:
        return SpanKind.CORRECTION
    if authority == SourceAuthority.RUNTIME_DIAGNOSTIC:
        return SpanKind.RUNTIME_DIAGNOSTIC
    if authority == SourceAuthority.ASSISTANT_CLAIM:
        return SpanKind.ASSISTANT_ANSWER
    return SpanKind.ASSERTION


def canonical_profile_slot(stable_key: str, *, category: str = "") -> str:
    raw = _lower(stable_key).replace(".", ":")
    if raw in PROFILE_SLOT_ALIASES:
        return PROFILE_SLOT_ALIASES[raw]
    if raw == "identity:name":
        return "identity.name"
    if raw.startswith("preference:"):
        return raw.replace(":", ".", 1)
    if _lower(category) == "preference" and raw:
        return f"preference.{raw.rsplit(':', 1)[-1]}"
    return raw.replace(":", ".", 1)


def canonical_graph_slot(*, attribute: str = "", predicate: str = "") -> str:
    key = _lower(predicate or attribute).replace(" ", "_")
    return GRAPH_RELATION_ALIASES.get(key, key.replace(":", "."))


def is_runtime_capability_slot(slot: str) -> bool:
    normalized = _lower(slot).replace(":", ".").replace(" ", "_")
    if normalized in CAPABILITY_SLOTS:
        return True
    # Boundary guard: capability/tool/runtime attributes are host diagnostics, not graph/profile truth.
    return any(part in normalized for part in ("shell_access", "terminal_access", "tool_access", "capability"))


def profile_claim_proposal(
    candidate: Mapping[str, Any],
    *,
    source: str,
    base_metadata: Mapping[str, Any],
    stable_key: str,
    category: str,
    content: str,
) -> ClaimProposal:
    meta = _metadata(candidate, base_metadata)
    authority = _authority_from_payload(meta, source=source)
    speaker = _speaker_from_payload(meta, authority)
    span_kind = _span_kind_from_payload(meta, authority)
    target_slot = canonical_profile_slot(stable_key, category=category)
    trace_id = _first_metadata_text(meta, ("trace_id", "correlation_id"))
    claim_seed = f"{source}|{stable_key}|{content}|{trace_id}"
    return ClaimProposal(
        claim_id=f"profile:{_hash_text(claim_seed)[:24]}",
        proposal_type="profile.identity" if target_slot.startswith("identity.") else "profile.preference",
        source_event_id=_first_metadata_text(meta, ("source_event_id", "event_id")),
        source_turn_id=_first_metadata_text(meta, ("source_turn_id", "turn_id")),
        source_span_id=_first_metadata_text(meta, ("source_span_id", "span_id")),
        turn_role=_first_metadata_text(meta, ("turn_role", "role", "source_role")),
        assertion_speaker=speaker,
        span_kind=span_kind,
        target_shelf="profile",
        target_slot=target_slot,
        target_scope=_first_metadata_text(meta, ("target_scope", "principal_scope", "scope")),
        storage_key=stable_key,
        subject=_text(candidate.get("subject") or "principal"),
        predicate=target_slot,
        surface_value=_first_metadata_text(meta, ("surface_value", "raw_user_span", "raw_value")),
        normalized_value=_first_metadata_text(meta, ("normalized_value", "canonical_value")),
        candidate_value=content,
        language=_first_metadata_text(meta, ("language", "lang")),
        normalization_method=_first_metadata_text(meta, ("normalization_method", "extractor")),
        authority_class=authority,
        confidence=float(candidate.get("confidence", meta.get("confidence", 0.0)) or 0.0),
        source_text_hash=_hash_text(content),
        trace_id=trace_id,
        metadata=meta,
    )


def graph_claim_proposal(
    candidate: Mapping[str, Any],
    *,
    source: str,
    base_metadata: Mapping[str, Any],
    target_kind: str,
    subject: str,
    predicate: str,
    value: str,
) -> ClaimProposal:
    meta = _metadata(candidate, base_metadata)
    authority = _authority_from_payload(meta, source=source)
    speaker = _speaker_from_payload(meta, authority)
    span_kind = _span_kind_from_payload(meta, authority)
    target_slot = canonical_graph_slot(attribute=predicate if target_kind == "state" else "", predicate=predicate)
    trace_id = _first_metadata_text(meta, ("trace_id", "correlation_id"))
    claim_seed = f"{source}|{subject}|{predicate}|{value}|{trace_id}"
    return ClaimProposal(
        claim_id=f"graph:{_hash_text(claim_seed)[:24]}",
        proposal_type="project.metadata" if target_slot.startswith("project.") else "graph.relation",
        source_event_id=_first_metadata_text(meta, ("source_event_id", "event_id")),
        source_turn_id=_first_metadata_text(meta, ("source_turn_id", "turn_id")),
        source_span_id=_first_metadata_text(meta, ("source_span_id", "span_id")),
        turn_role=_first_metadata_text(meta, ("turn_role", "role", "source_role")),
        assertion_speaker=speaker,
        span_kind=span_kind,
        target_shelf="graph",
        target_slot=target_slot,
        target_scope=_first_metadata_text(meta, ("target_scope", "project_scope", "scope")),
        storage_key=target_slot,
        subject=subject,
        predicate=predicate,
        surface_value=_first_metadata_text(meta, ("surface_value", "raw_user_span", "raw_value")),
        normalized_value=_first_metadata_text(meta, ("normalized_value", "canonical_value")),
        candidate_value=value,
        language=_first_metadata_text(meta, ("language", "lang")),
        normalization_method=_first_metadata_text(meta, ("normalization_method", "extractor")),
        authority_class=authority,
        confidence=float(candidate.get("confidence", meta.get("confidence", 0.0)) or 0.0),
        source_text_hash=_hash_text(f"{subject} {predicate} {value}"),
        trace_id=trace_id,
        metadata={**meta, "target_kind": target_kind},
    )


def _decision(
    proposal: ClaimProposal,
    *,
    decision: AdmissionDecisionType,
    reason_code: str,
    spec: SlotSpec | None = None,
    truth_eligible: bool = False,
    support_visibility: SupportVisibility = SupportVisibility.INSPECT_ONLY,
    supersede: bool = False,
    notes: str = "",
) -> AdmissionDecision:
    return AdmissionDecision(
        decision=decision,
        reason_code=reason_code,
        proposal=proposal,
        target_slot=spec.slot_id if spec else proposal.target_slot,
        storage_key=spec.storage_key if spec else proposal.storage_key,
        stable_key=spec.storage_key if spec else proposal.storage_key,
        truth_eligible=truth_eligible,
        support_visibility=support_visibility,
        supersede=supersede,
        policy_version=ADMISSION_POLICY_VERSION,
        slot_registry_version=SLOT_REGISTRY_VERSION,
        notes=notes,
    )


def admit_claim(proposal: ClaimProposal) -> AdmissionDecision:
    if not _text(proposal.admitted_value):
        return _decision(
            proposal,
            decision=AdmissionDecisionType.REJECT_CANDIDATE,
            reason_code=REASON_MISSING_VALUE,
        )
    if proposal.assertion_speaker in {AssertionSpeaker.ASSISTANT, AssertionSpeaker.QUOTED_ASSISTANT} or proposal.authority_class in {
        SourceAuthority.ASSISTANT_CLAIM,
        SourceAuthority.ASSISTANT_SELF_CLAIM,
    }:
        return _decision(
            proposal,
            decision=AdmissionDecisionType.MARK_CORRECTED_FALSE_EVENT,
            reason_code=REASON_ASSISTANT_CLAIM_NOT_USER_TRUTH,
            support_visibility=SupportVisibility.CONTRADICTION_ONLY,
        )
    if is_runtime_capability_slot(proposal.target_slot) or proposal.authority_class == SourceAuthority.RUNTIME_DIAGNOSTIC:
        return _decision(
            proposal,
            decision=AdmissionDecisionType.QUARANTINE_PROPOSAL,
            reason_code=REASON_RUNTIME_CAPABILITY_NOT_MEMORY_TRUTH,
            support_visibility=SupportVisibility.INSPECT_ONLY,
        )
    if proposal.target_shelf == "profile" and proposal.target_slot == "identity.name":
        return _decision(
            proposal,
            decision=AdmissionDecisionType.QUARANTINE_PROPOSAL,
            reason_code=REASON_GENERIC_IDENTITY_NAME_REJECTED,
            support_visibility=SupportVisibility.INSPECT_ONLY,
            notes="Derived writes must use identity.preferred_address_name or identity.platform_* slots.",
        )

    spec = SLOT_REGISTRY.get(proposal.target_slot)
    if spec is None:
        if proposal.target_shelf == "graph":
            return _decision(
                proposal,
                decision=AdmissionDecisionType.QUARANTINE_PROPOSAL,
                reason_code=REASON_UNKNOWN_DERIVED_GRAPH_SLOT,
                support_visibility=SupportVisibility.INSPECT_ONLY,
            )
        return _decision(
            proposal,
            decision=AdmissionDecisionType.QUARANTINE_PROPOSAL,
            reason_code=REASON_UNSUPPORTED_AUTHORITY,
            support_visibility=SupportVisibility.INSPECT_ONLY,
        )
    if proposal.authority_class in spec.forbidden_authorities:
        return _decision(
            proposal,
            decision=AdmissionDecisionType.REJECT_CANDIDATE,
            reason_code=REASON_UNSUPPORTED_AUTHORITY,
            spec=spec,
        )
    if proposal.authority_class in spec.supporting_authorities:
        return _decision(
            proposal,
            decision=AdmissionDecisionType.ACCEPT_SUPPORTING_EVENT,
            reason_code=REASON_UNSUPPORTED_AUTHORITY,
            spec=spec,
            truth_eligible=False,
            support_visibility=spec.default_support_visibility,
        )
    if proposal.authority_class not in spec.allowed_authorities:
        return _decision(
            proposal,
            decision=AdmissionDecisionType.QUARANTINE_PROPOSAL,
            reason_code=REASON_UNSUPPORTED_AUTHORITY,
            spec=spec,
        )
    decision_type = (
        AdmissionDecisionType.ACCEPT_WITH_SUPERSESSION
        if spec.exclusive_current or proposal.authority_class == SourceAuthority.USER_CORRECTION
        else AdmissionDecisionType.ACCEPT_DURABLE
    )
    return _decision(
        proposal,
        decision=decision_type,
        reason_code=REASON_ADMISSION_SUPERSESSION if decision_type == AdmissionDecisionType.ACCEPT_WITH_SUPERSESSION else REASON_ADMISSION_ACCEPTED,
        spec=spec,
        truth_eligible=True,
        support_visibility=SupportVisibility.ANSWER_EVIDENCE,
        supersede=decision_type == AdmissionDecisionType.ACCEPT_WITH_SUPERSESSION,
    )
