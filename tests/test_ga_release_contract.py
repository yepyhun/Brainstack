from __future__ import annotations

from scripts.ga_release_contract import GAReleaseInputs, evaluate_ga_verdict, known_limitation_record


def test_ready_blocked_conditional_semantics() -> None:
    ready = evaluate_ga_verdict(
        GAReleaseInputs(
            source_wizard_docker_parity=True,
            synthetic_gateway_e2e=True,
            live_smoke=True,
        )
    )
    blocked = evaluate_ga_verdict(GAReleaseInputs(source_wizard_docker_parity=True, synthetic_gateway_e2e=True))

    assert ready["verdict"] == "READY"
    assert ready["universal_bug_free_claim"] is False
    assert blocked["verdict"] == "BLOCKED"
    assert "LIVE_SMOKE_MISSING" in blocked["blocking"]


def test_manual_only_proof_cannot_mark_ready() -> None:
    verdict = evaluate_ga_verdict(
        GAReleaseInputs(
            manual_only_proof=True,
            source_wizard_docker_parity=True,
            synthetic_gateway_e2e=True,
            live_smoke=True,
        )
    )

    assert verdict["verdict"] == "BLOCKED"
    assert "MANUAL_ONLY_PROOF" in verdict["blocking"]


def test_known_limitation_cannot_hide_p0_p1() -> None:
    record = known_limitation_record(
        limitation_id="web_backend_not_configured",
        affected_use_case="URL inspection",
        mitigation="configured_unavailable diagnostic",
        blocks_ga=False,
        would_block_ga_if="assistant claims it browsed or guesses URL content",
    )

    assert record["blocks_ga"] is False
    assert "guesses URL content" in record["would_block_ga_if"]
