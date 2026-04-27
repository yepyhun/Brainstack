from __future__ import annotations

from brainstack.product_contracts import build_phrase_provenance_report


def test_phrase_provenance_traces_provider_output_to_firewall_drop() -> None:
    report = build_phrase_provenance_report(
        phrase="synthetic persona",
        timeline=[
            {
                "turn_id": "t1",
                "prompt_text": "normal prompt",
                "provider_output": "synthetic persona",
                "raw_transcript_stored": True,
                "continuity_candidate": "assistant_self_claim",
                "classification": "assistant_self_claim",
                "firewall_decision": "dropped",
            }
        ],
    )

    assert report["first_origin"]["type"] == "provider_generated"
    assert report["first_origin"]["not_in_prompt_before_turn"] is True
    assert report["final_verdict"] == "blocked_by_firewall"


def test_phrase_provenance_detects_prompt_source_if_present() -> None:
    report = build_phrase_provenance_report(
        phrase="prompt-born phrase",
        timeline=[
            {
                "turn_id": "t1",
                "prompt_text": "prompt-born phrase",
                "provider_output": "answer",
                "raw_transcript_stored": True,
                "firewall_decision": "dropped",
            }
        ],
    )

    assert report["first_origin"]["type"] == "prompt_source"
    assert report["first_origin"]["not_in_prompt_before_turn"] is False
