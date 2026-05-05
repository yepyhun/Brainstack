#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack import BrainstackMemoryProvider  # noqa: E402
from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from brainstack.style_contract import STYLE_CONTRACT_SLOT  # noqa: E402
from scripts.verify_behavior_card_delivery import (  # noqa: E402
    DEFAULT_HERMES_SOURCE,
    _contract_text,
    _rules,
    run as run_behavior_card_delivery,
)
from scripts.verify_projection_semantics_runtime_parity import (  # noqa: E402
    _brainstack_stats_stale_correction_events,
    verify_runtime_parity,
)


SCHEMA = "brainstack.agent_facing_memory_behavior_gauntlet.v1"
PUBLIC_PRIVATE_SENTINELS = (
    "private source text",
    "PUBLIC_SAFE_SENTINEL_SHOULD_NOT_APPEAR",
)


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def _payload_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _public_safe(value: Any) -> bool:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True)
    return not any(sentinel in payload for sentinel in PUBLIC_PRIVATE_SENTINELS)


def _case(name: str, *, passed: bool, summary: Mapping[str, Any], issues: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    issue_list = list(issues or [])
    return {
        "name": name,
        "status": "pass" if passed and not issue_list else "fail",
        "issues": issue_list,
        "summary": _json_clone(dict(summary)),
        "payload_hash": _payload_hash({"name": name, "summary": summary, "issues": issue_list}),
    }


def _provider(tmp_path: Path, *, session_id: str = "agent-facing-gauntlet") -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        session_id,
        platform="local-proof",
        user_id="user",
        agent_identity="agent-facing-gauntlet",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _case_behavior_card_delivery(hermes_source: Path) -> dict[str, Any]:
    report = run_behavior_card_delivery(hermes_source=hermes_source)
    session = dict(report.get("session_start") or {})
    compression = dict(report.get("post_compression") or {})
    inspect = dict(report.get("inspect") or {})
    summary = {
        "session_start_rule_count": session.get("rule_count"),
        "post_compression_rule_count": compression.get("rule_count"),
        "session_delivery_status": session.get("delivery_status"),
        "post_compression_delivery_status": compression.get("delivery_status"),
        "inspect_active_rule_count": inspect.get("active_rule_count"),
        "source_stable_key": session.get("source_stable_key"),
        "source_lane": session.get("source_lane"),
        "durable_behavior_rows": dict(report.get("durable_behavior_rows") or {}),
        "public_safe": _public_safe(report),
    }
    issues: list[dict[str, Any]] = []
    if report.get("status") != "pass":
        issues.append({"code": "behavior_card_delivery_verifier_failed", "observed": report.get("issues")})
    if session.get("rule_count") != 25 or compression.get("rule_count") != 25:
        issues.append({"code": "behavior_card_rule_count_mismatch", "summary": summary})
    if summary["source_stable_key"] != STYLE_CONTRACT_SLOT:
        issues.append({"code": "behavior_card_source_slot_mismatch", "observed": summary["source_stable_key"]})
    if not summary["public_safe"]:
        issues.append({"code": "behavior_card_report_not_public_safe"})
    return _case("active_behavior_card_session_and_compression", passed=not issues, summary=summary, issues=issues)


def _case_generic_profile_not_active_card(tmp_path: Path) -> dict[str, Any]:
    provider = _provider(tmp_path, session_id="generic-profile-not-card")
    try:
        assert provider._store is not None
        lines = _rules()
        provider._store.upsert_profile_item(
            stable_key="preference.generic_profile_style_notes_2026_05_04",
            category="work_context",
            content=_contract_text(lines),
            source="fixture:legacy_generic_profile",
            confidence=0.98,
            metadata=provider._scoped_metadata({"source_role": "user"}),
        )
        row = provider._store.get_profile_item(
            stable_key="preference.generic_profile_style_notes_2026_05_04",
            principal_scope_key=provider._principal_scope_key,
        )
        block = provider.system_prompt_block()
        trace = provider.behavior_policy_trace() or {}
        delivery = (
            dict(trace.get("system_prompt_block") or {}).get("active_preference_contract_delivery")
            if isinstance(trace, Mapping)
            else {}
        )
        delivery = dict(delivery or {})
        inspect = json.loads(provider.handle_tool_call("brainstack_inspect", {"query": "generic profile style notes"}))
        inspect_delivery = dict(inspect.get("report", {}).get("active_preference_delivery") or {})
        active_section_present = "# Brainstack Active User Preference Contract" in block
        profile_section_has_rules = "# Brainstack Profile" in block and any(line in block for line in lines[:3])
        summary = {
            "generic_profile_row_present": row is not None,
            "active_section_present": active_section_present,
            "profile_section_has_rules": profile_section_has_rules,
            "delivery_status": delivery.get("delivery_status"),
            "source_stable_key": delivery.get("source_stable_key"),
            "inspect_delivery_status": inspect_delivery.get("delivery_status"),
            "inspect_active_rule_count": inspect_delivery.get("active_rule_count"),
            "generic_profile_only_counted_as_active_card": bool(
                active_section_present
                and delivery.get("delivery_status") == "delivered_full"
                and delivery.get("source_stable_key") != STYLE_CONTRACT_SLOT
            ),
            "public_safe": _public_safe({"delivery": delivery, "inspect_delivery": inspect_delivery}),
        }
        issues: list[dict[str, Any]] = []
        if row is None:
            issues.append({"code": "generic_profile_fixture_missing"})
        if summary["generic_profile_only_counted_as_active_card"]:
            issues.append({"code": "generic_profile_satisfied_active_card"})
        if delivery.get("source_stable_key") == STYLE_CONTRACT_SLOT:
            issues.append({"code": "generic_profile_materialized_canonical_style_slot"})
        if not summary["public_safe"]:
            issues.append({"code": "generic_profile_trace_not_public_safe"})
        return _case("generic_profile_cannot_satisfy_active_card", passed=not issues, summary=summary, issues=issues)
    finally:
        provider.shutdown()


def _case_stale_diagnostic_projection() -> dict[str, Any]:
    report = verify_runtime_parity()
    fixture = dict(report.get("stale_correction_fixture") or {})
    summary = {
        "runtime_status": report.get("status"),
        "old_event_id": fixture.get("old_event_id"),
        "old_answer_decision": fixture.get("old_answer_decision"),
        "old_packet_action": fixture.get("old_packet_action"),
        "new_event_id": fixture.get("new_event_id"),
        "new_answer_decision": fixture.get("new_answer_decision"),
        "new_packet_action": fixture.get("new_packet_action"),
        "new_receipt_id_present": bool(fixture.get("new_receipt_id")),
        "public_safe": bool(report.get("public_safe")) and _public_safe(report),
    }
    issues: list[dict[str, Any]] = []
    if report.get("status") != "pass":
        issues.append({"code": "projection_runtime_parity_failed", "observed": report.get("issues")})
    if fixture.get("old_answer_decision") != "not_answer_safe" or fixture.get("old_packet_action") == "selected":
        issues.append({"code": "old_stale_support_answerable_or_selected", "fixture": fixture})
    if fixture.get("new_answer_decision") != "answer_safe" or fixture.get("new_packet_action") != "selected":
        issues.append({"code": "new_compact_truth_not_selected", "fixture": fixture})
    if not summary["public_safe"]:
        issues.append({"code": "stale_projection_report_not_public_safe"})
    return _case("stale_diagnostic_support_loses_to_new_truth", passed=not issues, summary=summary, issues=issues)


def _case_tool_and_packet_current_truth_agree(tmp_path: Path) -> dict[str, Any]:
    provider = _provider(tmp_path, session_id="current-truth-payload-agreement")
    try:
        assert provider._store is not None
        for event in _brainstack_stats_stale_correction_events():
            event = _json_clone(event)
            event.setdefault("scope", {})["principal_scope_key"] = provider._principal_scope_key
            provider._store.record_canonical_memory_event(event)

        query = "structured current truth request"
        inspect = json.loads(provider.handle_tool_call("brainstack_inspect", {"query": query}))
        inspect_view = dict(inspect.get("report", {}).get("current_truth_view") or {})
        packet = build_working_memory_packet(
            provider._store,
            query=query,
            session_id="current-truth-payload-agreement",
            principal_scope_key=provider._principal_scope_key,
            profile_match_limit=2,
            continuity_recent_limit=2,
            continuity_match_limit=2,
            transcript_match_limit=2,
            transcript_char_budget=400,
            evidence_item_budget=4,
            graph_limit=2,
            corpus_limit=2,
            corpus_char_budget=400,
            record_retrievals=False,
            adaptive_route_signals={"required_evidence_classes": ["current_truth"]},
        )
        packet_view = dict(packet.get("current_truth_view") or {})
        inspect_counters = dict(inspect_view.get("counters") or {})
        packet_counters = dict(packet_view.get("counters") or {})
        inspect_span = dict(inspect_view.get("source_event_span") or {})
        packet_span = dict(packet_view.get("source_event_span") or {})
        summary = {
            "inspect_status": inspect_view.get("status"),
            "packet_route_class": dict(packet.get("adaptive_route_plan") or {}).get("route_class"),
            "inspect_current_truth_row_count": inspect_view.get("current_truth_row_count"),
            "packet_current_truth_row_count": packet_view.get("current_truth_row_count"),
            "inspect_non_answerable_row_count": inspect_view.get("non_answerable_row_count"),
            "packet_non_answerable_row_count": packet_view.get("non_answerable_row_count"),
            "inspect_current_answerable_count": inspect_counters.get("current_answerable_count"),
            "packet_current_answerable_count": packet_counters.get("current_answerable_count"),
            "inspect_support_only_count": inspect_counters.get("support_only_count"),
            "packet_support_only_count": packet_counters.get("support_only_count"),
            "inspect_source_event_count": inspect_span.get("source_event_count"),
            "packet_source_event_count": packet_span.get("source_event_count"),
            "packet_ordinary_hot_path_rebuild": dict(packet_view.get("rebuild") or {}).get("ordinary_hot_path_rebuild"),
            "public_safe": _public_safe({"inspect_view": inspect_view, "packet_view": packet_view}),
        }
        issues: list[dict[str, Any]] = []
        expected_pairs = (
            ("current_truth_row_count", 1),
            ("non_answerable_row_count", 1),
            ("current_answerable_count", 1),
            ("support_only_count", 1),
            ("source_event_count", 2),
        )
        observed = {
            "current_truth_row_count": (summary["inspect_current_truth_row_count"], summary["packet_current_truth_row_count"]),
            "non_answerable_row_count": (summary["inspect_non_answerable_row_count"], summary["packet_non_answerable_row_count"]),
            "current_answerable_count": (summary["inspect_current_answerable_count"], summary["packet_current_answerable_count"]),
            "support_only_count": (summary["inspect_support_only_count"], summary["packet_support_only_count"]),
            "source_event_count": (summary["inspect_source_event_count"], summary["packet_source_event_count"]),
        }
        for field, expected in expected_pairs:
            left, right = observed[field]
            if left != expected or right != expected:
                issues.append({"code": "tool_packet_current_truth_mismatch", "field": field, "observed": [left, right], "expected": expected})
        if summary["packet_route_class"] != "current_truth":
            issues.append({"code": "packet_route_not_current_truth", "observed": summary["packet_route_class"]})
        if summary["packet_ordinary_hot_path_rebuild"] is not False:
            issues.append({"code": "packet_used_hot_path_rebuild", "observed": summary["packet_ordinary_hot_path_rebuild"]})
        if not summary["public_safe"]:
            issues.append({"code": "current_truth_payload_not_public_safe"})
        return _case("tool_inspect_and_packet_current_truth_agree", passed=not issues, summary=summary, issues=issues)
    finally:
        provider.shutdown()


def run_gauntlet(*, hermes_source: Path) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="brainstack-agent-facing-gauntlet-") as tmp:
        tmp_path = Path(tmp)
        cases.append(_case_behavior_card_delivery(hermes_source))
        cases.append(_case_generic_profile_not_active_card(tmp_path / "generic-profile"))
        cases.append(_case_stale_diagnostic_projection())
        cases.append(_case_tool_and_packet_current_truth_agree(tmp_path / "current-truth"))

    failed = [case for case in cases if case.get("status") != "pass"]
    report = {
        "schema": SCHEMA,
        "status": "pass" if not failed else "fail",
        "provider_llm_calls_performed": False,
        "optional_live_smoke_required": False,
        "case_count": len(cases),
        "failure_count": len(failed),
        "cases": cases,
        "payload_hashes": {str(case["name"]): case["payload_hash"] for case in cases},
        "failure_reasons": [
            f"{case['name']}:{issue.get('code')}"
            for case in failed
            for issue in list(case.get("issues") or [])
        ],
        "public_safe": _public_safe(cases),
    }
    if not report["public_safe"]:
        report["status"] = "fail"
        report["failure_reasons"].append("gauntlet_report_not_public_safe")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local agent-facing Brainstack memory behavior gauntlet without LLM calls.")
    parser.add_argument(
        "--hermes-source",
        default=os.environ.get("BRAINSTACK_RELEASE_HERMES_SOURCE", str(DEFAULT_HERMES_SOURCE)),
        help="Hermes source path used for the local MemoryManager session/compression seam.",
    )
    parser.add_argument("--out", type=Path, required=True, help="Path to write public-safe JSON report.")
    args = parser.parse_args()
    report = run_gauntlet(hermes_source=Path(args.hermes_source))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "failure_count": report["failure_count"], "failure_reasons": report["failure_reasons"]}, ensure_ascii=True, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
