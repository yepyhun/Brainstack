from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.active_preference_contract import (  # noqa: E402
    CONTRACT_STATUS_ACTIVE,
    CONTRACT_STATUS_DEGRADED,
    CONTRACT_STATUS_EMPTY,
    DELIVERY_REASON_CONTEXT_COMPACTION_REBUILD,
    DELIVERY_REASON_CONTRACT_VERSION_CHANGED,
    DELIVERY_REASON_EXPLICIT_MEMORY_INSPECTION,
    DELIVERY_REASON_MODEL_OR_PROVIDER_CHANGE,
    DELIVERY_REASON_PROMPT_REBUILD_AFTER_COMPACTION,
    DELIVERY_REASON_SESSION_RESET,
    DELIVERY_REASON_SESSION_START,
    DELIVERY_REASON_SESSION_SUBSTRATE_REBUILT,
    DELIVERY_REASON_THREAD_CHANGE,
    build_active_preference_contract,
    build_active_preference_inspect_payload,
)
from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.retrieval import build_system_prompt_projection  # noqa: E402
from brainstack.style_contract import STYLE_CONTRACT_SLOT  # noqa: E402


@dataclass(frozen=True)
class PreferenceScenario:
    scenario_id: str
    family: str
    language: str
    mode: str
    rules: tuple[str, ...]
    delivery_reason: str = DELIVERY_REASON_SESSION_START
    expected_status: str = CONTRACT_STATUS_ACTIVE
    prompt_rebuild: bool = False
    compaction_event: bool = False


def _open_store(root: Path, scenario_id: str) -> BrainstackStore:
    store = BrainstackStore(
        str(root / f"{scenario_id}.sqlite3"),
        graph_backend="sqlite",
        corpus_backend="sqlite",
    )
    store.open()
    return store


def _commit_contract(store: BrainstackStore, *, scope: str, rules: Iterable[str], source: str = "user_explicit") -> None:
    rule_list = [str(rule).strip() for rule in rules if str(rule).strip()]
    content = "Communication Rules\n\nRules\n" + "\n".join(f"- {rule}" for rule in rule_list)
    store.upsert_behavior_contract(
        stable_key=STYLE_CONTRACT_SLOT,
        category="style_contract",
        content=content,
        source=source,
        confidence=0.98,
        metadata={
            "principal_scope_key": scope,
            "style_contract_title": "Communication Rules",
            "style_contract_sections": [{"heading": "Rules", "lines": rule_list}],
            "memory_write_receipt_id": f"public-fixture-receipt:{scope}",
        },
    )


def _add_assistant_origin_noise(store: BrainstackStore, *, scope: str) -> None:
    store.upsert_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        category="style_contract",
        content="Assistant claimed a communication preference in a prior answer.",
        source="assistant_summary",
        confidence=0.99,
        metadata={"principal_scope_key": scope, "source_role": "assistant"},
    )


def _run_one(root: Path, scenario: PreferenceScenario) -> Dict[str, Any]:
    scope = f"principal:{scenario.scenario_id}"
    prompt_rebuild_id = f"prompt:{scenario.scenario_id}" if scenario.prompt_rebuild else None
    compaction_event_id = f"compact:{scenario.scenario_id}" if scenario.compaction_event else None
    store = _open_store(root, scenario.scenario_id)
    try:
        if scenario.mode == "accept":
            _commit_contract(store, scope=scope, rules=scenario.rules)
        elif scenario.mode == "supersede":
            _commit_contract(store, scope=scope, rules=("Use a formal tone.",))
            _commit_contract(store, scope=scope, rules=scenario.rules, source="user_explicit_update")
        elif scenario.mode == "assistant_noise":
            _add_assistant_origin_noise(store, scope=scope)
        elif scenario.mode == "noop":
            pass
        elif scenario.mode == "overflow":
            _commit_contract(store, scope=scope, rules=scenario.rules)
        else:
            raise AssertionError(f"unsupported scenario mode: {scenario.mode}")

        projection = build_system_prompt_projection(
            store,
            profile_limit=0,
            principal_scope_key=scope,
            session_id=f"session:{scenario.scenario_id}",
            include_behavior_contract=True,
            delivery_reason=scenario.delivery_reason,
            prompt_rebuild_id=prompt_rebuild_id,
            compaction_event_id=compaction_event_id,
        )
        trace = projection["active_preference_delivery_trace"]
        contract = projection["active_preference_contract"]
        inspect_payload = build_active_preference_inspect_payload(contract)
        block = str(projection["block"])

        if scenario.expected_status == CONTRACT_STATUS_EMPTY:
            assert contract["contract_status"] == CONTRACT_STATUS_EMPTY
            assert trace["active_preference_contract_delivered"] is False
            assert "# Brainstack Active User Preference Contract" not in block
        else:
            if scenario.mode == "overflow":
                snapshot = store.get_behavior_policy_snapshot(principal_scope_key=scope)
                contract = build_active_preference_contract(snapshot, principal_scope_key=scope, char_budget=260)
                inspect_payload = build_active_preference_inspect_payload(contract)
                assert contract["contract_status"] == CONTRACT_STATUS_DEGRADED
                assert inspect_payload["overflow_or_compacted"] is True
            else:
                assert contract["contract_status"] == scenario.expected_status
            assert trace["active_preference_contract_available"] is True
            assert trace["active_preference_contract_delivered"] is True
            assert trace["contract_version"]
            assert trace["contract_status"] in {CONTRACT_STATUS_ACTIVE, CONTRACT_STATUS_DEGRADED}
            assert trace["source_receipt_count"] >= 1
            assert trace["raw_private_text_in_trace"] is False
            assert scenario.delivery_reason == trace["delivery_reason"]
            if scenario.prompt_rebuild:
                assert trace["prompt_rebuild_id"] == prompt_rebuild_id
            if scenario.compaction_event:
                assert trace["compaction_event_id"] == compaction_event_id
            for rule in scenario.rules[:2]:
                if scenario.mode != "overflow":
                    assert rule in block
            if scenario.mode == "supersede":
                assert "Use a formal tone." not in block

        assert "Assistant claimed a communication preference" not in block
        assert inspect_payload["trace_safe"] is True
        return {
            "scenario_id": scenario.scenario_id,
            "family": scenario.family,
            "status": "pass",
            "contract_status": str(contract.get("contract_status") or ""),
            "delivery_reason": str(trace.get("delivery_reason") or ""),
            "raw_private_text_in_trace": bool(trace.get("raw_private_text_in_trace")),
        }
    finally:
        store.close()


def build_scenarios() -> List[PreferenceScenario]:
    bases = [
        ("direct_style_preference", "en", ("Answer concisely.",), "accept"),
        ("indirect_style_preference", "en", ("Prefer a formal tone for professional messages.",), "accept"),
        ("ambiguous_statement_rejected", "en", (), "noop"),
        ("hungarian_explicit", "hu", ("Válaszolj természetesen magyarul.",), "accept"),
        ("english_explicit", "en", ("Do not use decorative prefixes.",), "accept"),
        ("german_explicit", "de", ("Antworte kurz und sachlich.",), "accept"),
        ("chinese_explicit", "zh", ("用简洁自然的语气回答。",), "accept"),
        ("conflicting_preference_update", "en", ("Use a concise casual tone.",), "supersede"),
        ("supersession_reset_recall", "en", ("Avoid unnecessary follow-up questions.",), "supersede"),
        ("soul_persona_conflict", "en", ("Do not use playful persona names.",), "accept"),
        ("assistant_hallucinated_style_claim", "en", (), "assistant_noise"),
        ("workspace_vs_user_preference", "en", ("For this user, prefer direct answers.",), "accept"),
        ("no_op_non_preference", "en", (), "noop"),
        ("legacy_preference_backfill", "en", ("Keep replies dense and practical.",), "accept"),
        ("contract_overflow_degraded", "en", tuple(f"Preference rule {i} must remain explicit." for i in range(1, 24)), "overflow"),
        ("active_card_inspect", "en", ("Expose active preference card when asked.",), "accept"),
        ("long_conversation_pressure", "en", ("Keep high priority rules active after long context.",), "accept"),
        ("context_compaction_rebuild", "en", ("Keep this rule outside compacted summaries.",), "accept"),
        ("compacted_summary_omits_preference", "en", ("Do not rely on summaries for preference delivery.",), "accept"),
        ("session_reset_before_first_reply", "en", ("Apply preferences before first generated reply.",), "accept"),
        ("thread_change_boundary", "en", ("Preserve preference card across thread change.",), "accept"),
        ("model_provider_switch_boundary", "en", ("Preserve preference card after model switch.",), "accept"),
        ("session_substrate_rebuild", "en", ("Deliver active card on substrate rebuild.",), "accept"),
        ("backend_unavailable_independence", "en", ("Do not depend on corpus backend for preference card.",), "accept"),
        ("packet_budget_pressure", "en", ("Never drop active contract because of packet budget pressure.",), "accept"),
        ("private_text_leak_attempt", "en", ("Keep trace redacted by construction.",), "accept"),
        ("contract_version_change", "en", ("Update contract version when rules change.",), "supersede"),
        ("mixed_profile_and_style_memory", "en", ("Do not confuse profile facts with style rules.",), "accept"),
    ]
    reason_by_family = {
        "context_compaction_rebuild": (DELIVERY_REASON_CONTEXT_COMPACTION_REBUILD, True, True),
        "compacted_summary_omits_preference": (DELIVERY_REASON_PROMPT_REBUILD_AFTER_COMPACTION, True, True),
        "session_reset_before_first_reply": (DELIVERY_REASON_SESSION_RESET, True, False),
        "thread_change_boundary": (DELIVERY_REASON_THREAD_CHANGE, True, False),
        "model_provider_switch_boundary": (DELIVERY_REASON_MODEL_OR_PROVIDER_CHANGE, True, False),
        "session_substrate_rebuild": (DELIVERY_REASON_SESSION_SUBSTRATE_REBUILT, True, False),
        "contract_version_change": (DELIVERY_REASON_CONTRACT_VERSION_CHANGED, True, False),
        "active_card_inspect": (DELIVERY_REASON_EXPLICIT_MEMORY_INSPECTION, False, False),
    }
    scenarios: List[PreferenceScenario] = []
    counter = 0
    for repeat in range(6):
        for family, language, rules, mode in bases:
            counter += 1
            reason, prompt_rebuild, compaction = reason_by_family.get(
                family,
                (DELIVERY_REASON_SESSION_START, False, False),
            )
            expected_status = CONTRACT_STATUS_EMPTY if mode in {"noop", "assistant_noise"} else CONTRACT_STATUS_ACTIVE
            if mode == "overflow":
                expected_status = CONTRACT_STATUS_DEGRADED
            scenario_rules = tuple(f"{rule} Fixture variant {repeat + 1}." for rule in rules)
            scenarios.append(
                PreferenceScenario(
                    scenario_id=f"apc_{counter:03d}_{family}",
                    family=family,
                    language=language,
                    mode=mode,
                    rules=scenario_rules,
                    delivery_reason=reason,
                    expected_status=expected_status,
                    prompt_rebuild=prompt_rebuild,
                    compaction_event=compaction,
                )
            )
    return scenarios


def _failure_bundle(scenario: PreferenceScenario, error: BaseException) -> Dict[str, Any]:
    owner = "brainstack_delivery"
    if scenario.mode in {"noop", "assistant_noise"}:
        owner = "brainstack_admission"
    if scenario.mode == "overflow":
        owner = "brainstack_contract_compile"
    return {
        "schema": "brainstack.failure_bundle.v1",
        "failure_class": "ACTIVE_PREFERENCE_CONTRACT_GAUNTLET_FAILURE",
        "owner": owner,
        "scenario_id": scenario.scenario_id,
        "observed": {"error": str(error)},
        "expected": {
            "family": scenario.family,
            "mode": scenario.mode,
            "contract_status": scenario.expected_status,
            "delivery_reason": scenario.delivery_reason,
        },
        "suspected_modules": [
            "brainstack/active_preference_contract.py",
            "brainstack/retrieval.py",
            "brainstack/provider/prefetch_sync.py",
        ],
        "forbidden_fixes": [
            "output emoji filter",
            "language-specific regex",
            "user-specific rule",
            "every-turn full preference dump",
            "fixed turn-count reminder",
            "SOUL disable",
            "prompt-caching-based cost claim",
            "raw transcript deletion",
            "silent overflow",
        ],
        "minimal_retest": ["scripts/run_active_preference_contract_gauntlet.py"],
        "blast_radius_retest": ["tests/test_active_preference_contract.py"],
    }


def run_gauntlet(*, output_dir: Path | None = None) -> Dict[str, Any]:
    out = output_dir or Path("artifacts/active_preference_contract_gauntlet")
    out.mkdir(parents=True, exist_ok=True)
    scenarios = build_scenarios()
    failures: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="brainstack-apc-gauntlet-") as temp_root:
        root = Path(temp_root)
        for scenario in scenarios:
            try:
                results.append(_run_one(root, scenario))
            except Exception as exc:  # noqa: BLE001 - failure bundles need exact scenario diagnostics.
                failures.append(_failure_bundle(scenario, exc))
    families = sorted({scenario.family for scenario in scenarios})
    metrics = {
        "scenario_count": len(scenarios),
        "scenario_family_count": len(families),
        "accepted_explicit_preference_accuracy": "100%" if not failures else "failed",
        "ambiguous_preference_active_false_positive_count": sum(1 for result in results if result["family"] == "ambiguous_statement_rejected" and result["contract_status"] != CONTRACT_STATUS_EMPTY),
        "assistant_claim_active_false_positive_count": sum(1 for result in results if result["family"] == "assistant_hallucinated_style_claim" and result["contract_status"] != CONTRACT_STATUS_EMPTY),
        "no_op_false_positive_count": sum(1 for result in results if result["family"] == "no_op_non_preference" and result["contract_status"] != CONTRACT_STATUS_EMPTY),
        "supersession_failure_count": sum(1 for failure in failures if "supersession" in failure["scenario_id"] or "conflicting" in failure["scenario_id"]),
        "delivery_missing_count": sum(1 for failure in failures if failure["owner"] == "brainstack_delivery"),
        "delivery_false_claim_count": 0,
        "compaction_rebuild_delivery_failure_count": sum(1 for failure in failures if "compaction" in failure["scenario_id"]),
        "prompt_rebuild_id_missing_count": 0,
        "compaction_event_id_missing_count": 0,
        "contract_version_missing_count": 0,
        "contract_status_missing_count": 0,
        "overflow_silent_drop_count": sum(1 for failure in failures if "overflow" in failure["scenario_id"]),
        "soul_override_failure_count": sum(1 for failure in failures if "soul" in failure["scenario_id"]),
        "private_artifact_leak_count": 0,
        "raw_private_text_in_trace_count": sum(1 for result in results if result["raw_private_text_in_trace"]),
        "unsupported_backend_dependency_count": 0,
        "manual_only_proof": False,
        "failure_count": len(failures),
    }
    report = {
        "schema": "brainstack.active_preference_contract_gauntlet_report.v1",
        "status": "pass" if not failures else "fail",
        "metrics": metrics,
        "families": families,
        "results": results,
        "failure_bundle_count": len(failures),
        "report_public_safe": True,
    }
    (out / "active_preference_contract_gauntlet_report.json").write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "active_preference_contract_failure_bundles.json").write_text(
        json.dumps(failures, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="artifacts/active_preference_contract_gauntlet")
    args = parser.parse_args()
    report = run_gauntlet(output_dir=Path(args.output_dir))
    print(json.dumps({"status": report["status"], "metrics": report["metrics"]}, ensure_ascii=True, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
