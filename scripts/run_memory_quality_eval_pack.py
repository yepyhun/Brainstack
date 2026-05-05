#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack import BrainstackMemoryProvider  # noqa: E402
from scripts.run_agent_facing_memory_behavior_gauntlet import run_gauntlet  # noqa: E402
from scripts.run_local_workload_performance_replay import build_report as build_workload_report  # noqa: E402
from scripts.verify_behavior_card_delivery import DEFAULT_HERMES_SOURCE  # noqa: E402
from scripts.verify_profile_scope_index import build_report as build_profile_scope_report  # noqa: E402
from scripts.verify_projection_semantics_runtime_parity import verify_runtime_parity  # noqa: E402


SCHEMA = "brainstack.memory_quality_eval_pack.v1"
PRIVATE_SENTINELS = ("private source text", "PUBLIC_SAFE_SENTINEL_SHOULD_NOT_APPEAR")


def _public_safe(value: Any) -> bool:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True)
    return not any(sentinel in payload for sentinel in PRIVATE_SENTINELS)


def _case(
    *,
    case_id: str,
    category: str,
    owner_module: str,
    owner_phase: str,
    description: str,
    expected: Any,
    observed: Any,
    predicate: Callable[[Any], bool],
) -> dict[str, Any]:
    passed = bool(predicate(observed))
    return {
        "case_id": case_id,
        "category": category,
        "owner_module": owner_module,
        "owner_phase": owner_phase,
        "description": description,
        "expected": expected,
        "observed": observed,
        "status": "pass" if passed else "fail",
    }


def _case_by_name(report: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    for case in report.get("cases") or []:
        if isinstance(case, Mapping) and case.get("name") == name:
            return case
    return {}


def _perf_case(report: Mapping[str, Any], case_id: str) -> Mapping[str, Any]:
    for case in report.get("cases") or []:
        if isinstance(case, Mapping) and case.get("case_id") == case_id:
            return case
    return {}


def _provider_negative_cases() -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="brainstack-quality-negative-") as tmp:
        provider = BrainstackMemoryProvider(
            {
                "db_path": str(Path(tmp) / "brainstack.sqlite3"),
                "graph_backend": "sqlite",
                "corpus_backend": "sqlite",
            }
        )
        provider.initialize(
            "memory-quality-negative",
            platform="local-proof",
            user_id="user",
            agent_identity="agent-quality",
            agent_workspace="workspace",
        )
        try:
            recall = json.loads(provider.handle_tool_call("brainstack_recall", {"query": "unknown public-safe missing fact"}))
            schemas = provider.get_tool_schemas()
            tool_names = {str(schema.get("name") or "") for schema in schemas}
            proactive = json.loads(provider.handle_tool_call("brainstack_proactive_status", {}))
            inspect = json.loads(provider.handle_tool_call("brainstack_inspect", {"query": "unknown public-safe missing fact"}))
        finally:
            provider.shutdown()
    return [
        _case(
            case_id="unknown_memory_is_unanswerable",
            category="uncertainty",
            owner_module="brainstack.provider.recall",
            owner_phase="264",
            description="Unknown memory must not become answer truth.",
            expected=False,
            observed=bool(dict(recall.get("memory_answerability") or {}).get("can_answer")),
            predicate=lambda value: value is False,
        ),
        _case(
            case_id="no_scheduler_executor_approval_tools",
            category="proactive_negative",
            owner_module="brainstack.provider.tools",
            owner_phase="269",
            description="Brainstack tool surface must not expose scheduler/executor/approval governor tools.",
            expected="no execute/schedule/approve tools",
            observed=sorted(name for name in tool_names if any(token in name for token in ("execute", "schedule", "approve"))),
            predicate=lambda value: value == [],
        ),
        _case(
            case_id="proactive_status_read_only",
            category="proactive_negative",
            owner_module="brainstack.proactive_agent_contract",
            owner_phase="254",
            description="Proactive status must be read-only status, not a scheduler wake or notification side effect.",
            expected=True,
            observed=bool(proactive.get("read_only")),
            predicate=lambda value: value is True,
        ),
        _case(
            case_id="inspect_unknown_public_safe",
            category="inspectability",
            owner_module="brainstack.provider.inspection",
            owner_phase="264",
            description="Inspect output for unknown memory must remain public-safe.",
            expected=True,
            observed=_public_safe(inspect),
            predicate=lambda value: value is True,
        ),
    ]


def build_eval_pack(*, hermes_source: Path = DEFAULT_HERMES_SOURCE) -> dict[str, Any]:
    agent = run_gauntlet(hermes_source=hermes_source)
    projection = verify_runtime_parity()
    performance = build_workload_report()
    scope = build_profile_scope_report()

    behavior = _case_by_name(agent, "active_behavior_card_session_and_compression")
    behavior_summary = dict(behavior.get("summary") or {})
    generic = _case_by_name(agent, "generic_profile_cannot_satisfy_active_card")
    generic_summary = dict(generic.get("summary") or {})
    tool_packet = _case_by_name(agent, "tool_inspect_and_packet_current_truth_agree")
    tool_packet_summary = dict(tool_packet.get("summary") or {})

    fixture = dict(projection.get("stale_correction_fixture") or {})
    perf_summary = dict(performance.get("summary") or {})
    no_memory = _perf_case(performance, "no_memory_minimal")
    profile_only = _perf_case(performance, "profile_only")
    current_truth = _perf_case(performance, "current_truth_lookup")
    stale_perf = _perf_case(performance, "stale_correction")
    deep = _perf_case(performance, "corpus_semantic_supported")
    tight = _perf_case(performance, "tight_packet_budget")
    scoped_lookup = _perf_case(performance, "scoped_profile_lookup")
    scope_diag = dict(scope.get("diagnostics") or {})

    cases: list[dict[str, Any]] = [
        _case(case_id="agent_gauntlet_passes", category="agent_facing", owner_module="scripts.run_agent_facing_memory_behavior_gauntlet", owner_phase="264", description="Agent-facing gauntlet must pass.", expected="pass", observed=agent.get("status"), predicate=lambda v: v == "pass"),
        _case(case_id="agent_gauntlet_no_llm", category="agent_facing", owner_module="scripts.run_agent_facing_memory_behavior_gauntlet", owner_phase="264", description="Base agent-facing eval must not call provider LLM.", expected=False, observed=agent.get("provider_llm_calls_performed"), predicate=lambda v: v is False),
        _case(case_id="behavior_card_session_25_rules", category="behavior_card", owner_module="brainstack.active_preference_contract", owner_phase="258.2", description="Session-start behavior card must contain all 25 public-safe rules.", expected=25, observed=behavior_summary.get("session_start_rule_count"), predicate=lambda v: v == 25),
        _case(case_id="behavior_card_compression_25_rules", category="behavior_card", owner_module="brainstack.active_preference_contract", owner_phase="258.2", description="Post-compression behavior card must contain all 25 public-safe rules.", expected=25, observed=behavior_summary.get("post_compression_rule_count"), predicate=lambda v: v == 25),
        _case(case_id="behavior_card_canonical_slot", category="behavior_card", owner_module="brainstack.style_contract", owner_phase="258.1", description="Active behavior card must use canonical style-contract slot.", expected="preference:style_contract", observed=behavior_summary.get("source_stable_key"), predicate=lambda v: v == "preference:style_contract"),
        _case(case_id="behavior_card_profile_lane", category="behavior_card", owner_module="brainstack.storage.profile_store", owner_phase="259", description="Active behavior card projection must come from profile style lane.", expected="profile_style_contract", observed=behavior_summary.get("source_lane"), predicate=lambda v: v == "profile_style_contract"),
        _case(case_id="behavior_card_no_durable_behavior_rows", category="behavior_card", owner_module="brainstack.storage.profile_store", owner_phase="259", description="Profile-lane fallback must not create durable behavior/compiled rows.", expected={"behavior_contracts": 0, "compiled_behavior_policies": 0}, observed=behavior_summary.get("durable_behavior_rows"), predicate=lambda v: dict(v or {}).get("behavior_contracts") == 0 and dict(v or {}).get("compiled_behavior_policies") == 0),
        _case(case_id="generic_profile_not_active_card", category="behavior_card", owner_module="brainstack.active_preference_contract", owner_phase="264", description="Generic profile rows must not satisfy active-card delivery.", expected=False, observed=generic_summary.get("generic_profile_only_counted_as_active_card"), predicate=lambda v: v is False),
        _case(case_id="generic_profile_delivery_not_delivered", category="behavior_card", owner_module="brainstack.provider.prefetch_sync", owner_phase="264", description="Generic-only row should not show delivered active-card status.", expected="not_delivered", observed=generic_summary.get("delivery_status"), predicate=lambda v: v == "not_delivered"),
        _case(case_id="projection_runtime_passes", category="projection_semantics", owner_module="brainstack.projection_inspect", owner_phase="253", description="Projection semantics runtime parity must pass.", expected="pass", observed=projection.get("status"), predicate=lambda v: v == "pass"),
        _case(case_id="stale_old_not_answer_safe", category="stale_truth", owner_module="brainstack.projection_semantics", owner_phase="253", description="Old large diagnostics support must be non-answerable.", expected="not_answer_safe", observed=fixture.get("old_answer_decision"), predicate=lambda v: v == "not_answer_safe"),
        _case(case_id="stale_old_dropped_from_packet", category="stale_truth", owner_module="brainstack.core.packet_budget", owner_phase="253", description="Old large diagnostics support must not be selected into answer packet.", expected="not selected", observed=fixture.get("old_packet_action"), predicate=lambda v: v != "selected"),
        _case(case_id="stale_new_answer_safe", category="stale_truth", owner_module="brainstack.projection_semantics", owner_phase="253", description="New compact diagnostics truth must be answer-safe.", expected="answer_safe", observed=fixture.get("new_answer_decision"), predicate=lambda v: v == "answer_safe"),
        _case(case_id="stale_new_selected", category="stale_truth", owner_module="brainstack.core.packet_budget", owner_phase="253", description="New compact diagnostics truth must be selected.", expected="selected", observed=fixture.get("new_packet_action"), predicate=lambda v: v == "selected"),
        _case(case_id="stale_new_receipt_present", category="stale_truth", owner_module="brainstack.memory_write_receipts", owner_phase="256", description="New compact diagnostics truth must carry a receipt.", expected=True, observed=bool(fixture.get("new_receipt_id")), predicate=lambda v: v is True),
        _case(case_id="projection_unsafe_selected_empty", category="answerability", owner_module="brainstack.projection_conformance", owner_phase="253", description="Projection parity must not select unsafe answer events.", expected=[], observed=projection.get("unsafe_selected_event_ids"), predicate=lambda v: v == []),
        _case(case_id="projection_public_safe", category="inspectability", owner_module="brainstack.projection_inspect", owner_phase="253", description="Projection inspect/doctor output must be public-safe.", expected=True, observed=projection.get("public_safe"), predicate=lambda v: v is True),
        _case(case_id="projection_doctor_active", category="inspectability", owner_module="brainstack.projection_inspect", owner_phase="253", description="Projection doctor must be active.", expected="active", observed=projection.get("doctor_status"), predicate=lambda v: v == "active"),
        _case(case_id="tool_packet_current_truth_route", category="current_truth", owner_module="brainstack.control_plane", owner_phase="264", description="Tool/packet current-truth agreement case must route as current truth.", expected="current_truth", observed=tool_packet_summary.get("packet_route_class"), predicate=lambda v: v == "current_truth"),
        _case(case_id="tool_packet_current_truth_counts", category="current_truth", owner_module="brainstack.current_truth_view", owner_phase="264", description="Tool and packet must agree on one current and one non-answerable row.", expected=[1, 1], observed=[tool_packet_summary.get("packet_current_truth_row_count"), tool_packet_summary.get("packet_non_answerable_row_count")], predicate=lambda v: v == [1, 1]),
        _case(case_id="performance_replay_passes", category="performance", owner_module="scripts.run_local_workload_performance_replay", owner_phase="265", description="Local workload replay must pass.", expected="pass", observed=performance.get("status"), predicate=lambda v: v == "pass"),
        _case(case_id="hard_gated_semantic_zero", category="performance", owner_module="brainstack.adaptive_route_plan", owner_phase="257", description="Hard-gated routes must make zero semantic backend calls.", expected=0, observed=perf_summary.get("hard_gated_semantic_backend_calls"), predicate=lambda v: v == 0),
        _case(case_id="no_memory_shelf_zero", category="performance", owner_module="brainstack.retrieval_pipeline", owner_phase="258", description="No-memory route must not call shelves.", expected=0, observed=sum(int(v or 0) for v in dict(no_memory.get("shelf_backend_calls") or {}).values()), predicate=lambda v: v == 0),
        _case(case_id="profile_route_no_graph_corpus", category="performance", owner_module="brainstack.retrieval_pipeline", owner_phase="258", description="Profile route must not call graph/corpus shelves.", expected=[0, 0], observed=[dict(profile_only.get("shelf_backend_calls") or {}).get("search_graph"), dict(profile_only.get("shelf_backend_calls") or {}).get("search_corpus")], predicate=lambda v: v == [0, 0]),
        _case(case_id="current_truth_no_rebuild", category="performance", owner_module="brainstack.storage.current_truth_l0_store", owner_phase="261", description="Current-truth ordinary read must not rebuild from canonical events.", expected=0, observed=current_truth.get("current_truth_rebuild_calls"), predicate=lambda v: v == 0),
        _case(case_id="stale_perf_semantic_zero", category="performance", owner_module="brainstack.adaptive_route_plan", owner_phase="257", description="Stale correction current-truth route must not call semantic backend.", expected=0, observed=stale_perf.get("semantic_backend_call_total"), predicate=lambda v: v == 0),
        _case(case_id="deep_route_keeps_semantic", category="performance", owner_module="brainstack.retrieval_pipeline", owner_phase="257", description="Deep semantic-supported route must still call semantic backend.", expected=">0", observed=deep.get("semantic_backend_call_total"), predicate=lambda v: int(v or 0) > 0),
        _case(case_id="profile_like_fallback_zero", category="scope_isolation", owner_module="brainstack.storage.profile_read_store", owner_phase="262", description="Normal profile scope lookup must not use LIKE fallback.", expected=0, observed=perf_summary.get("profile_like_fallback_count"), predicate=lambda v: v == 0),
        _case(case_id="protected_truth_drop_zero", category="packet_budget", owner_module="brainstack.core.packet_budget", owner_phase="265", description="Replay must not drop protected truth.", expected=0, observed=perf_summary.get("protected_truth_drop_attempts"), predicate=lambda v: v == 0),
        _case(case_id="tight_budget_has_tokens", category="packet_budget", owner_module="brainstack.core.packet_budget", owner_phase="265", description="Tight budget case must exercise real candidate tokens.", expected=">0", observed=tight.get("packet_token_estimate"), predicate=lambda v: int(v or 0) > 0),
        _case(case_id="scope_index_1000_principals", category="scope_isolation", owner_module="brainstack.storage.profile_read_store", owner_phase="262", description="Scope index proof must cover 1000 principals.", expected=1000, observed=scope.get("principal_count"), predicate=lambda v: v == 1000),
        _case(case_id="scope_index_used", category="scope_isolation", owner_module="brainstack.storage.profile_read_store", owner_phase="262", description="Profile scope lookup must use indexed path.", expected=">=1", observed=scope_diag.get("indexed_lookup_count"), predicate=lambda v: int(v or 0) >= 1),
        _case(case_id="scope_like_fallback_zero", category="scope_isolation", owner_module="brainstack.storage.profile_read_store", owner_phase="262", description="Profile scope index verifier must not use LIKE fallback.", expected=0, observed=scope_diag.get("like_fallback_count"), predicate=lambda v: v == 0),
        _case(case_id="scope_query_plan_uses_index", category="scope_isolation", owner_module="brainstack.storage.profile_read_store", owner_phase="262", description="SQLite query plan must use profile scope lookup index.", expected="idx_profile_scope_lookup", observed=scope.get("indexed_query_plan"), predicate=lambda v: "idx_profile_scope_lookup" in str(v or "")),
        _case(case_id="scoped_replay_lookup_hit", category="scope_isolation", owner_module="brainstack.storage.profile_read_store", owner_phase="265", description="Replay scoped profile lookup must hit requested principal.", expected=True, observed=scoped_lookup.get("lookup_hit"), predicate=lambda v: v is True),
        *_provider_negative_cases(),
    ]

    failed = [case for case in cases if case["status"] != "pass"]
    categories = sorted({str(case["category"]) for case in cases})
    failure_to_owner: dict[str, list[str]] = {}
    for case in failed:
        key = f"{case['owner_phase']}:{case['owner_module']}"
        failure_to_owner.setdefault(key, []).append(case["case_id"])
    public_safe = _public_safe(cases)
    if not public_safe:
        failure_to_owner.setdefault("eval_pack:public_safety", []).append("eval_pack_public_safe")

    return {
        "schema": SCHEMA,
        "status": "pass" if not failed and public_safe else "fail",
        "case_count": len(cases),
        "failure_count": len(failed) + (0 if public_safe else 1),
        "categories": categories,
        "llm_calls_performed": False,
        "optional_live_smoke_required": False,
        "public_safe": public_safe,
        "failure_to_owner": failure_to_owner,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic public-safe Brainstack memory-quality eval pack.")
    parser.add_argument("--hermes-source", type=Path, default=DEFAULT_HERMES_SOURCE)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build_eval_pack(hermes_source=args.hermes_source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "case_count": report["case_count"], "failure_count": report["failure_count"]}, ensure_ascii=True, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
