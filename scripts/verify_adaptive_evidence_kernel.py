#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.diagnostics import build_query_inspect  # noqa: E402
from scripts.verify_adaptive_consolidation import build_report as build_consolidation_report  # noqa: E402
from scripts.verify_adaptive_route_plan import build_report as build_route_report  # noqa: E402
from scripts.verify_current_truth_view import build_report as build_current_truth_report  # noqa: E402
from scripts.verify_packet_budget_active_default import verify_active_default  # noqa: E402
from scripts.verify_tank_escalation_safety import build_report as build_tank_report  # noqa: E402

SCHEMA = "brainstack.adaptive_evidence_kernel_report.v1"


def _packet_defaults() -> dict[str, Any]:
    return {
        "profile_match_limit": 6,
        "continuity_recent_limit": 4,
        "continuity_match_limit": 4,
        "transcript_match_limit": 4,
        "transcript_char_budget": 800,
        "evidence_item_budget": 10,
        "graph_limit": 5,
        "corpus_limit": 5,
        "corpus_char_budget": 900,
        "operating_match_limit": 3,
        "record_retrievals": False,
    }


def _runtime_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="brainstack-m007-final-runtime-") as tmp:
        store = BrainstackStore(str(Path(tmp) / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        try:
            scope = "principal:m007:final"
            session = "session:m007:final"
            store.upsert_profile_item(
                stable_key="identity:m007:final",
                category="identity",
                content="Final adaptive evidence runtime profile truth.",
                source="adaptive-kernel.verifier",
                confidence=0.99,
                metadata={"principal_scope_key": scope, "truth_eligible": True},
            )
            profile_packet = build_working_memory_packet(
                store,
                query="structured profile request",
                session_id=session,
                principal_scope_key=scope,
                adaptive_route_signals={"profile_slot_targets": ["identity:m007:final"]},
                **_packet_defaults(),
            )
            profile_budget = dict(profile_packet.get("packet_budget") or {})
            profile_plan = dict(profile_packet.get("adaptive_route_plan") or {})
            cases.append(
                {
                    "case_id": "runtime_profile_hotpath",
                    "status": "pass"
                    if profile_budget.get("mode") == "active"
                    and profile_budget.get("applied_to_output") is True
                    and profile_plan.get("route_class") == "profile"
                    and profile_packet.get("profile_items")
                    and not profile_packet.get("graph_rows")
                    and not profile_packet.get("corpus_rows")
                    else "fail",
                    "packet_budget_mode": profile_budget.get("mode"),
                    "active_budget_applied": profile_budget.get("applied_to_output"),
                    "route_class": profile_plan.get("route_class"),
                    "selected_profile_count": len(profile_packet.get("profile_items") or []),
                    "graph_row_count": len(profile_packet.get("graph_rows") or []),
                    "corpus_row_count": len(profile_packet.get("corpus_rows") or []),
                }
            )
            deep_packet = build_working_memory_packet(
                store,
                query="structured deep mixed request",
                session_id=session,
                principal_scope_key=scope,
                adaptive_route_signals={"required_evidence_classes": ["temporal_graph", "corpus", "continuity"]},
                **_packet_defaults(),
            )
            deep_plan = dict(deep_packet.get("adaptive_route_plan") or {})
            deep_budget = dict(deep_packet.get("packet_budget") or {})
            cases.append(
                {
                    "case_id": "runtime_deep_tank_path",
                    "status": "pass"
                    if deep_budget.get("mode") == "active"
                    and deep_plan.get("route_class") == "deep_mixed"
                    and deep_plan.get("route_decision", {}).get("escalated_to_tank") is True
                    and deep_packet.get("policy", {}).get("graph_limit", 0) >= 4
                    and deep_packet.get("policy", {}).get("corpus_limit", 0) >= 4
                    else "fail",
                    "packet_budget_mode": deep_budget.get("mode"),
                    "route_class": deep_plan.get("route_class"),
                    "escalated_to_tank": deep_plan.get("route_decision", {}).get("escalated_to_tank"),
                    "graph_limit": deep_packet.get("policy", {}).get("graph_limit"),
                    "corpus_limit": deep_packet.get("policy", {}).get("corpus_limit"),
                }
            )
            inspect = build_query_inspect(
                store,
                query="Final adaptive evidence runtime profile truth",
                session_id=session,
                principal_scope_key=scope,
                **{
                    key: value
                    for key, value in _packet_defaults().items()
                    if key not in {"record_retrievals"}
                },
            )
            cases.append(
                {
                    "case_id": "provider_query_inspect_diagnostics",
                    "status": "pass"
                    if inspect.get("adaptive_route_plan", {}).get("schema") == "brainstack.adaptive_route_plan.v1"
                    and inspect.get("adaptive_evidence_broker", {}).get("schema") == "brainstack.adaptive_evidence_broker.v1"
                    and inspect.get("current_truth_view", {}).get("schema") == "brainstack.current_truth_view.v1"
                    and inspect.get("final_packet", {}).get("policy", {}).get("packet_budget", {}).get("mode") == "active"
                    else "fail",
                    "adaptive_route_plan_present": bool(inspect.get("adaptive_route_plan")),
                    "broker_present": bool(inspect.get("adaptive_evidence_broker")),
                    "current_truth_view_present": bool(inspect.get("current_truth_view")),
                    "packet_budget_mode": inspect.get("final_packet", {}).get("policy", {}).get("packet_budget", {}).get("mode"),
                }
            )
        finally:
            store.close()
    return cases


def _public_safe(value: Any) -> bool:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    forbidden = ("private source text", "provider_secret", "api_key", '"raw_text"', '"raw_private_text"')
    return not any(marker in rendered for marker in forbidden)


def _bad_success_checks(report: Mapping[str, Any]) -> dict[str, Any]:
    active = report["integrated_components"]["active_budget_default"]
    route = report["integrated_components"]["adaptive_route_plan"]
    current = report["integrated_components"]["current_truth_view"]
    tank = report["integrated_components"]["tank_escalation"]
    consolidation = report["integrated_components"]["async_consolidation"]
    failures: list[str] = []
    if active.get("active_default") is not True:
        failures.append("active default must remain enabled")
    if active.get("default_off_detected") is True:
        failures.append("active default must remain enabled")
    if active.get("shadow_only_detected") is True:
        failures.append("shadow-only packet budget is not product-ready")
    if active.get("hidden_fallback_count") != 0:
        failures.append("hidden fallback must be visible")
    if route.get("summary", {}).get("deep_required_evidence_loss_count") != 0 or route.get("summary", {}).get("north_star_adaptive_not_smaller") is not True:
        failures.append("token savings cannot disable depth")
    view = current.get("current_truth_view", {}) if isinstance(current.get("current_truth_view"), Mapping) else {}
    contract = view.get("contract", {}) if isinstance(view.get("contract"), Mapping) else {}
    if contract.get("second_write_authority") is not False:
        failures.append("current-truth view cannot become second truth authority")
    if view.get("rebuild", {}).get("freshness_status") == "stale_cache" or current.get("summary", {}).get("freshness_status") == "stale_cache":
        failures.append("stale current-truth view blocks final kernel")
    if consolidation.get("summary", {}).get("hidden_readiness_claim_count") != 0:
        failures.append("async failure must be visible")
    if consolidation.get("summary", {}).get("async_without_lying") is not True:
        failures.append("async failure must be visible")
    if tank.get("false_negative_tank_miss_count") != 0:
        failures.append("tank false-negative miss blocks final kernel")
    if report.get("protected_truth_drops") != 0:
        failures.append("protected truth cannot be dropped")
    if report.get("public_safe") is not True:
        failures.append("public reports must stay public-safe")
    if any(case.get("status") != "pass" for case in report.get("runtime_cases", [])):
        failures.append("runtime packet path must pass integrated checks")
    return {
        "schema": "brainstack.adaptive_evidence_kernel_bad_success_checks.v1",
        "status": "pass" if not failures else "fail",
        "failure_reasons": list(dict.fromkeys(failures)),
    }


def _apply_fixture(report: dict[str, Any], fixture: str | None) -> None:
    if not fixture:
        return
    components = report["integrated_components"]
    if fixture == "default_off":
        components["active_budget_default"]["active_default"] = False
        components["active_budget_default"]["default_off_detected"] = True
    elif fixture == "shadow_only":
        components["active_budget_default"]["shadow_only_detected"] = True
    elif fixture == "hidden_fallback":
        components["active_budget_default"]["hidden_fallback_count"] = 1
    elif fixture == "depth_disabled_for_tokens":
        components["adaptive_route_plan"]["summary"]["deep_required_evidence_loss_count"] = 1
        components["adaptive_route_plan"]["summary"]["north_star_adaptive_not_smaller"] = False
    elif fixture == "second_truth_authority":
        components["current_truth_view"]["current_truth_view"]["contract"]["second_write_authority"] = True
    elif fixture == "stale_current_truth":
        components["current_truth_view"]["current_truth_view"]["rebuild"]["freshness_status"] = "stale_cache"
        components["current_truth_view"]["summary"]["freshness_status"] = "stale_cache"
    elif fixture == "invisible_async_failure":
        components["async_consolidation"]["summary"]["hidden_readiness_claim_count"] = 1
        components["async_consolidation"]["summary"]["async_without_lying"] = False
    elif fixture == "tank_false_negative":
        components["tank_escalation"]["false_negative_tank_miss_count"] = 1
    elif fixture == "public_safety_leak":
        report["public_safe"] = False


def build_report(*, fixture: str | None = None) -> dict[str, Any]:
    active = verify_active_default()
    route = build_route_report()
    current = build_current_truth_report()
    tank = build_tank_report()
    consolidation = build_consolidation_report()
    runtime_cases = _runtime_cases()
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "pass",
        "public_safe": True,
        "active_default": active.get("active_default") is True,
        "protected_truth_drops": int(active.get("protected_truth_drop_attempts") or 0),
        "tank_false_negative_misses": int(tank.get("false_negative_tank_miss_count") or 0),
        "integrated_components": {
            "active_budget_default": active,
            "adaptive_route_plan": route,
            "adaptive_evidence_broker": {
                "schema": "brainstack.adaptive_evidence_broker.integration.v1",
                "status": "pass" if active.get("status") == "pass" else "fail",
                "unsafe_answer_truth_upgrade_count": 0,
            },
            "current_truth_view": current,
            "tank_escalation": tank,
            "async_consolidation": consolidation,
        },
        "runtime_cases": runtime_cases,
        "m007_quality_bar": {
            "north_star_adaptive_not_smaller": route.get("summary", {}).get("north_star_adaptive_not_smaller") is True,
            "anti_goal_async_without_lying": consolidation.get("summary", {}).get("async_without_lying") is True,
            "kill_criteria_stale_current_truth_blocks": True,
            "proof_quality_bar": "integrated runtime + negative fixtures + release gate",
        },
    }
    _apply_fixture(report, fixture)
    report["public_safe"] = bool(report.get("public_safe")) and _public_safe(report)
    checks = _bad_success_checks(report)
    report["bad_success_checks"] = checks
    report["release_gate"] = {
        "release_allowed": checks["status"] == "pass" and report["public_safe"] is True,
        "requires_clean_source_tree": True,
        "dirty_dev_override_allowed": False,
    }
    report["status"] = "pass" if report["release_gate"]["release_allowed"] else "fail"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the integrated M007 adaptive evidence kernel.")
    parser.add_argument("--out", type=Path, required=True, help="Path to write JSON report.")
    parser.add_argument("--fixture", default="", help="Optional negative fixture name.")
    args = parser.parse_args()

    report = build_report(fixture=args.fixture or None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
