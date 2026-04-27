from __future__ import annotations

from pathlib import Path

from scripts.ga_release_contract import GAReleaseInputs, evaluate_ga_verdict, known_limitation_record


ROOT = Path(__file__).resolve().parents[1]


def read_doc(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_ga_release_contract_has_supported_scope() -> None:
    text = read_doc("SUPPORTED_ENVIRONMENTS.md")

    assert "source of truth -> wizard install -> latest Hermes checkout -> Docker image" in text
    assert "live Discord bot smoke" in text
    assert "Manual Discord prompt transcript as sole proof" in text


def test_ga_release_contract_has_non_goals() -> None:
    text = read_doc("NON_GOALS_AND_KNOWN_LIMITS.md")

    assert "No claim that Brainstack is bug-free in every environment" in text
    assert "No Brainstack-owned output governor" in text
    assert "No Hungarian-specific durable write parser" in text


def test_feature_freeze_blocks_new_feature_expansion() -> None:
    text = read_doc("FEATURE_FREEZE_POLICY.md")

    assert "GA hardening is not feature expansion" in text
    assert "New donor lift" in text
    assert "Live-case phrase blacklist" in text


def test_p0_p1_taxonomy_blocks_core_risks() -> None:
    text = read_doc("P0_P1_FAILURE_TAXONOMY.md")
    lowered = text.casefold()

    for required in (
        "capability",
        "approval",
        "assistant hallucinated",
        "source, wizard install, docker image",
        "support-only",
        "current assignment",
    ):
        assert required in lowered


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
