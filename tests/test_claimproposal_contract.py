from __future__ import annotations

from brainstack.core.admission import AssertionSpeaker, ClaimProposal, SourceAuthority, SpanKind


def test_claimproposal_required_fields() -> None:
    proposal = ClaimProposal(
        claim_id="c1",
        proposal_type="profile.identity",
        target_slot="identity.preferred_address_name",
        target_scope="principal",
        surface_value="raw span",
        normalized_value="Alex",
        candidate_value="raw span",
        source_event_id="e1",
        source_span_id="s1",
        assertion_speaker=AssertionSpeaker.USER,
        span_kind=SpanKind.ASSERTION,
        authority_class=SourceAuthority.USER_EXPLICIT_ASSERTION,
        language="hu",
        normalization_method="llm_structured_extraction",
    )

    assert proposal.admitted_value == "Alex"
    assert proposal.normalization_method == "llm_structured_extraction"
