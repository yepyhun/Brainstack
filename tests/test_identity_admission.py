from __future__ import annotations

from brainstack.admission_policy import admit_claim
from brainstack.core.admission import (
    AdmissionDecisionType,
    AssertionSpeaker,
    ClaimProposal,
    SourceAuthority,
    SpanKind,
)


def test_identity_platform_handle_not_preferred_name() -> None:
    handle = ClaimProposal(
        claim_id="handle",
        target_shelf="profile",
        target_slot="identity.platform_handle",
        candidate_value="ExampleHandle",
        authority_class=SourceAuthority.TRUSTED_HOST,
        assertion_speaker=AssertionSpeaker.TRUSTED_HOST,
        span_kind=SpanKind.ASSERTION,
    )
    preferred = ClaimProposal(
        claim_id="preferred",
        target_shelf="profile",
        target_slot="identity.preferred_address_name",
        candidate_value="Alex",
        authority_class=SourceAuthority.USER_EXPLICIT_ASSERTION,
        assertion_speaker=AssertionSpeaker.USER,
        span_kind=SpanKind.ASSERTION,
    )

    assert admit_claim(handle).target_slot == "identity.platform_handle"
    assert admit_claim(preferred).target_slot == "identity.preferred_address_name"


def test_no_generic_identity_name_slot() -> None:
    proposal = ClaimProposal(
        claim_id="bad",
        target_shelf="profile",
        target_slot="identity.name",
        candidate_value="ExampleHandle",
        authority_class=SourceAuthority.TIER2_SUMMARY,
        assertion_speaker=AssertionSpeaker.UNKNOWN,
    )

    decision = admit_claim(proposal)
    assert decision.decision == AdmissionDecisionType.QUARANTINE_PROPOSAL
    assert decision.reason_code == "GENERIC_IDENTITY_NAME_REJECTED"
