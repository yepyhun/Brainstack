from __future__ import annotations

from brainstack.admission_policy import admit_claim
from brainstack.core.admission import (
    AdmissionDecisionType,
    AssertionSpeaker,
    ClaimProposal,
    SourceAuthority,
    SpanKind,
    SupportVisibility,
)


def _project(slot: str, authority: SourceAuthority = SourceAuthority.USER_EXPLICIT_ASSERTION) -> ClaimProposal:
    return ClaimProposal(
        claim_id=slot,
        proposal_type="project.metadata",
        target_shelf="graph",
        target_slot=slot,
        target_scope="project:brainstack",
        candidate_value="value",
        normalized_value="value",
        authority_class=authority,
        assertion_speaker=AssertionSpeaker.USER if authority == SourceAuthority.USER_EXPLICIT_ASSERTION else AssertionSpeaker.UNKNOWN,
        span_kind=SpanKind.ASSERTION,
    )


def test_project_created_by_user_explicit_admitted() -> None:
    decision = admit_claim(_project("project.created_by"))

    assert decision.decision == AdmissionDecisionType.ACCEPT_DURABLE
    assert decision.truth_eligible is True


def test_project_inspired_by_user_explicit_admitted() -> None:
    decision = admit_claim(_project("project.inspired_by"))

    assert decision.decision == AdmissionDecisionType.ACCEPT_DURABLE


def test_project_repo_url_user_explicit_admitted_without_fetch() -> None:
    decision = admit_claim(_project("project.repo_url"))

    assert decision.decision == AdmissionDecisionType.ACCEPT_DURABLE
    assert decision.target_slot == "project.repo_url"


def test_assistant_project_claim_support_only() -> None:
    proposal = _project("project.created_by", SourceAuthority.ASSISTANT_CLAIM)
    proposal = ClaimProposal(**{**proposal.__dict__, "assertion_speaker": AssertionSpeaker.ASSISTANT})

    decision = admit_claim(proposal)
    assert decision.decision == AdmissionDecisionType.MARK_CORRECTED_FALSE_EVENT
    assert decision.support_visibility == SupportVisibility.CONTRADICTION_ONLY


def test_tier2_project_claim_proposal_only() -> None:
    decision = admit_claim(_project("project.created_by", SourceAuthority.TIER2_SUMMARY))

    assert decision.decision == AdmissionDecisionType.QUARANTINE_PROPOSAL

