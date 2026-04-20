# ruff: noqa: E402
"""Targeted regression tests for phase 42.1 typed final-output enforcement."""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location(
    "phase42_1_host_import_shims",
    _host_shims_path,
)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider
from brainstack.output_contract import (
    OUTPUT_ENFORCEMENT_MODE_STRICT,
    validate_output_against_contract,
)


def _compiled_policy(*clauses):
    return {"clauses": list(clauses)}


def _clause(*, kind: str, compiled_short_form: str, constraint_code: str = "", clause_id: str = "rule-1"):
    return {
        "id": clause_id,
        "status": "active",
        "kind": kind,
        "compiled_short_form": compiled_short_form,
        "constraint_code": constraint_code,
    }


def _make_provider(tmp_path: Path, session_id: str) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        config={
            "db_path": str(tmp_path / "brainstack.db"),
            "ordinary_reply_output_validation_enabled": True,
        }
    )
    provider.initialize(
        session_id,
        hermes_home=str(tmp_path),
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="workspace-a",
    )
    return provider


def test_repairable_typed_invariants_report_repaired_status():
    result = validate_output_against_contract(
        content="**Szia** — hello 😀",
        compiled_policy=_compiled_policy(
            _clause(
                kind="punctuation_policy",
                compiled_short_form="Do not use em dash punctuation in replies.",
                constraint_code="forbid_em_dash_only",
                clause_id="rule-dash",
            ),
            _clause(
                kind="forbidden_surface_form",
                compiled_short_form="Do not use emoji.",
                clause_id="rule-emoji",
            ),
            _clause(
                kind="formatting_policy",
                compiled_short_form="Do not use markdown boldface.",
                clause_id="rule-bold",
            ),
        ),
    )

    assert result["status"] == "repaired"
    assert result["blocked"] is False
    assert result["can_ship"] is True
    assert result["changed"] is True
    assert result["remaining_violations"] == []
    assert result["content"] == "Szia - hello "
    assert {item["enforcement"] for item in result["repairs"]} == {"repair"}


def test_non_repairable_typed_invariants_report_advisory_status_for_ordinary_reply():
    result = validate_output_against_contract(
        content="Lets dive in - most.",
        compiled_policy=_compiled_policy(
            _clause(
                kind="punctuation_policy",
                compiled_short_form="Do not use dash punctuation in replies.",
                constraint_code="forbid_all_dash_like",
                clause_id="rule-dash",
            ),
            _clause(
                kind="forbidden_surface_form",
                compiled_short_form="Do not say lets dive in.",
                clause_id="rule-phrase",
            ),
        ),
    )

    assert result["status"] == "advisory"
    assert result["blocked"] is False
    assert result["can_ship"] is True
    assert result["block_reason"] == ""
    assert len(result["remaining_violations"]) == 2
    assert {item["enforcement"] for item in result["remaining_violations"]} == {"advisory"}


def test_non_repairable_typed_invariants_can_still_be_strictly_verified():
    result = validate_output_against_contract(
        content="Lets dive in - most.",
        compiled_policy=_compiled_policy(
            _clause(
                kind="punctuation_policy",
                compiled_short_form="Do not use dash punctuation in replies.",
                constraint_code="forbid_all_dash_like",
                clause_id="rule-dash",
            ),
            _clause(
                kind="forbidden_surface_form",
                compiled_short_form="Do not say lets dive in.",
                clause_id="rule-phrase",
            ),
        ),
        enforcement_mode=OUTPUT_ENFORCEMENT_MODE_STRICT,
    )

    assert result["status"] == "blocked"
    assert result["blocked"] is True
    assert result["can_ship"] is False
    assert result["block_reason"] == "non_repairable_typed_invariant_violation"
    assert len(result["remaining_violations"]) == 2
    assert {item["enforcement"] for item in result["remaining_violations"]} == {"block"}


def test_provider_trace_records_advisory_final_output_validation(tmp_path):
    provider = _make_provider(tmp_path, "phase42-1-advisory")
    try:
        store = provider._store
        assert store is not None
        store.upsert_behavior_contract(
            category="preference",
            content=(
                "User style contract\n\n"
                "rules:\n"
                "1. Always respond in Hungarian.\n"
                "2. Do not use dash punctuation in replies.\n"
            ),
            source="test",
            confidence=1.0,
            metadata={"principal_scope_key": provider._principal_scope_key},
        )

        result = provider.validate_assistant_output("Rossz - valasz")
        assert result is not None
        assert result["status"] == "advisory"
        assert result["blocked"] is False
        assert result["can_ship"] is True

        provider.record_output_validation_delivery(result, delivered_content="Kuldes tanacsadva")
        trace = provider.behavior_policy_trace()
        assert trace is not None
        final = trace["final_output_validation"]
        assert final["status"] == "advisory"
        assert final["blocked"] is False
        assert final["remaining_violation_count"] == 1
        assert final["delivered"] is True
        assert final["delivered_status"] == "advisory"
        assert final["delivered_blocked"] is False
    finally:
        provider.shutdown()
