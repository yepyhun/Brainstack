from __future__ import annotations

from brainstack.source_integrity import (
    build_source_integrity_envelope,
    is_source_backed_truth_answerable,
    public_source_integrity_status,
    verify_source_integrity_transition,
)


def test_source_drift_blocks_answerable_truth_until_readmitted() -> None:
    previous = build_source_integrity_envelope(
        source_handle="/private/docs/source.md",
        source_adapter="source_sync_local",
        source_scope="principal:test",
        content_hash="hash-old",
        receipt_id="receipt-old",
        truth_eligible=True,
    )
    current = build_source_integrity_envelope(
        source_handle="/private/docs/source.md",
        source_adapter="source_sync_local",
        source_scope="principal:test",
        content_hash="hash-new",
        receipt_id="",
        truth_eligible=True,
    )

    transition = verify_source_integrity_transition(previous=previous, current=current)

    assert transition["status"] == "blocked"
    assert transition["reason_code"] == "SOURCE_DRIFT_REQUIRES_READMISSION"
    assert transition["durable_truth_mutation_allowed"] is False
    assert transition["next_safe_action"] == "re_admit_from_updated_source"
    assert is_source_backed_truth_answerable(transition["current_envelope"]) is False


def test_public_source_integrity_status_is_bounded_and_private_safe() -> None:
    envelope = build_source_integrity_envelope(
        source_handle="/home/private/source.md",
        source_adapter="source_sync_local",
        source_scope="platform:test|user_id:user|agent_identity:agent",
        content_hash="hash-current",
        receipt_id="receipt-current",
        truth_eligible=True,
    )

    status = public_source_integrity_status(envelope)

    assert status["status"] == "fresh"
    assert status["answerable_truth_allowed"] is True
    assert status["raw_private_source_in_status"] is False
    assert "/home/private" not in str(status)


def test_missing_source_fingerprint_blocks_truth_answerability() -> None:
    envelope = build_source_integrity_envelope(
        source_handle="source:public",
        source_adapter="source_sync_local",
        source_scope="principal:test",
        content_hash="",
        receipt_id="receipt-current",
        truth_eligible=True,
    )

    assert envelope["drift_status"] == "missing_fingerprint"
    assert is_source_backed_truth_answerable(envelope) is False
