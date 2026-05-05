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

from brainstack import BrainstackMemoryProvider  # noqa: E402
from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402
from scripts.verify_behavior_card_delivery import _rules, _write_style_rules  # noqa: E402
from scripts.verify_projection_semantics_runtime_parity import _brainstack_stats_stale_correction_events  # noqa: E402


SCHEMA = "brainstack.local_workload_performance_replay.v1"


class WorkloadSpyStore(BrainstackStore):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.semantic_calls: dict[str, int] = {
            "search_semantic_evidence": 0,
            "search_conversation_semantic": 0,
            "search_corpus_semantic": 0,
        }
        self.shelf_calls: dict[str, int] = {
            "list_profile_items": 0,
            "search_profile": 0,
            "search_continuity": 0,
            "recent_continuity": 0,
            "search_transcript": 0,
            "search_transcript_global": 0,
            "search_operating_records": 0,
            "search_graph": 0,
            "search_corpus": 0,
        }
        self.current_truth_rebuild_calls = 0

    def _record_shelf(self, name: str) -> None:
        self.shelf_calls[name] = int(self.shelf_calls.get(name) or 0) + 1

    def search_semantic_evidence(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.semantic_calls["search_semantic_evidence"] += 1
        return []

    def search_conversation_semantic(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.semantic_calls["search_conversation_semantic"] += 1
        return []

    def search_corpus_semantic(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.semantic_calls["search_corpus_semantic"] += 1
        return []

    def list_profile_items(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record_shelf("list_profile_items")
        return super().list_profile_items(*args, **kwargs)

    def search_profile(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record_shelf("search_profile")
        return super().search_profile(*args, **kwargs)

    def search_continuity(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record_shelf("search_continuity")
        return super().search_continuity(*args, **kwargs)

    def recent_continuity(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record_shelf("recent_continuity")
        return super().recent_continuity(*args, **kwargs)

    def search_transcript(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record_shelf("search_transcript")
        return super().search_transcript(*args, **kwargs)

    def search_transcript_global(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record_shelf("search_transcript_global")
        return super().search_transcript_global(*args, **kwargs)

    def search_operating_records(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record_shelf("search_operating_records")
        return super().search_operating_records(*args, **kwargs)

    def search_graph(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record_shelf("search_graph")
        return super().search_graph(*args, **kwargs)

    def search_corpus(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record_shelf("search_corpus")
        return super().search_corpus(*args, **kwargs)

    def list_canonical_memory_events(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.current_truth_rebuild_calls += 1
        return super().list_canonical_memory_events(*args, **kwargs)


def _open_spy(path: Path) -> WorkloadSpyStore:
    store = WorkloadSpyStore(str(path), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _seed_profile(store: BrainstackStore, *, principal_scope_key: str = "principal:test") -> None:
    store.upsert_profile_item(
        stable_key="identity:name",
        category="identity",
        content="ExampleUser profile truth for structured profile request.",
        source="fixture:performance_replay",
        confidence=0.99,
        metadata={"principal_scope_key": principal_scope_key},
    )


def _seed_current_truth(store: BrainstackStore, *, principal_scope_key: str = "principal:test") -> None:
    for event in _brainstack_stats_stale_correction_events():
        payload = json.loads(json.dumps(event, ensure_ascii=True))
        payload.setdefault("scope", {})["principal_scope_key"] = principal_scope_key
        store.record_canonical_memory_event(payload)


def _protected_drop_attempts(packet_budget: Mapping[str, Any]) -> int:
    if packet_budget.get("answer_evidence_preserved") is False:
        return 1
    if packet_budget.get("receipt_coverage_preserved") is False:
        return 1
    if packet_budget.get("authority_fields_preserved") is False:
        return 1
    return 0


def _run_packet_case(
    root: Path,
    *,
    case_id: str,
    query: str,
    signals: Mapping[str, Any],
    seed: str = "",
    packet_budget_max_candidate_tokens: int | None = None,
) -> dict[str, Any]:
    store = _open_spy(root / f"{case_id}.sqlite3")
    try:
        principal = "principal:test"
        if seed in {"profile", "tight_budget"}:
            _seed_profile(store, principal_scope_key=principal)
        if seed in {"current_truth", "stale_correction"}:
            _seed_current_truth(store, principal_scope_key=principal)
        if hasattr(store, "reset_profile_scope_lookup_diagnostics"):
            store.reset_profile_scope_lookup_diagnostics()
        store.current_truth_rebuild_calls = 0
        packet = build_working_memory_packet(
            store,
            query=query,
            session_id=f"session:{case_id}",
            principal_scope_key=principal,
            profile_match_limit=6,
            continuity_recent_limit=4,
            continuity_match_limit=4,
            transcript_match_limit=4,
            transcript_char_budget=800,
            evidence_item_budget=10,
            graph_limit=5,
            corpus_limit=5,
            corpus_char_budget=900,
            record_retrievals=False,
            packet_budget_mode="active",
            packet_budget_max_candidate_tokens=packet_budget_max_candidate_tokens,
            adaptive_route_signals=dict(signals),
        )
        profile_lookup = (
            store.profile_scope_lookup_diagnostics()
            if hasattr(store, "profile_scope_lookup_diagnostics")
            else {}
        )
        packet_budget = dict(packet.get("packet_budget") or {})
        return {
            "case_id": case_id,
            "route_class": dict(packet.get("adaptive_route_plan") or {}).get("route_class"),
            "semantic_backend_calls": dict(store.semantic_calls),
            "semantic_backend_call_total": sum(int(value or 0) for value in store.semantic_calls.values()),
            "shelf_backend_calls": dict(store.shelf_calls),
            "current_truth_rebuild_calls": store.current_truth_rebuild_calls,
            "profile_like_fallback_count": int(profile_lookup.get("like_fallback_count") or 0),
            "profile_indexed_lookup_count": int(profile_lookup.get("indexed_lookup_count") or 0),
            "packet_token_estimate": int(packet_budget.get("estimated_tokens_before") or 0),
            "packet_selected_tokens": int(packet_budget.get("selected_candidate_tokens") or 0),
            "packet_dropped_tokens": int(packet_budget.get("dropped_candidate_tokens") or 0),
            "packet_budget_status": packet_budget.get("status"),
            "protected_truth_drop_attempts": _protected_drop_attempts(packet_budget),
            "current_truth_row_count": int(dict(packet.get("current_truth_view") or {}).get("current_truth_row_count") or 0),
            "non_answerable_row_count": int(dict(packet.get("current_truth_view") or {}).get("non_answerable_row_count") or 0),
            "ordinary_hot_path_rebuild": dict(dict(packet.get("current_truth_view") or {}).get("rebuild") or {}).get("ordinary_hot_path_rebuild"),
        }
    finally:
        store.close()


def _run_scoped_profile_lookup_case(root: Path) -> dict[str, Any]:
    store = _open_spy(root / "scoped_profile_lookup.sqlite3")
    try:
        for index in range(100):
            scope = f"principal:{index}"
            store.upsert_profile_item(
                stable_key="style.reply_tone",
                category="style_preference",
                content=f"Reply tone for {scope}.",
                source="fixture:performance_replay",
                confidence=0.9,
                metadata={"principal_scope_key": scope},
            )
        store.reset_profile_scope_lookup_diagnostics()
        row = store.get_profile_item(stable_key="style.reply_tone", principal_scope_key="principal:42")
        diag = store.profile_scope_lookup_diagnostics()
        return {
            "case_id": "scoped_profile_lookup",
            "route_class": "profile_scope_index",
            "semantic_backend_calls": dict(store.semantic_calls),
            "semantic_backend_call_total": 0,
            "shelf_backend_calls": dict(store.shelf_calls),
            "current_truth_rebuild_calls": store.current_truth_rebuild_calls,
            "profile_like_fallback_count": int(diag.get("like_fallback_count") or 0),
            "profile_indexed_lookup_count": int(diag.get("indexed_lookup_count") or 0),
            "profile_exact_storage_fallback_count": int(diag.get("exact_storage_fallback_count") or 0),
            "lookup_hit": bool(row and row.get("principal_scope_key") == "principal:42"),
            "packet_token_estimate": 0,
            "packet_selected_tokens": 0,
            "packet_dropped_tokens": 0,
            "packet_budget_status": "not_applicable",
            "protected_truth_drop_attempts": 0,
            "current_truth_row_count": 0,
            "non_answerable_row_count": 0,
            "ordinary_hot_path_rebuild": False,
        }
    finally:
        store.close()


def _run_behavior_card_prompt_case(root: Path) -> dict[str, Any]:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(root / "behavior_card_prompt.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "behavior-card-performance",
        platform="local-proof",
        user_id="user",
        agent_identity="agent-performance-replay",
        agent_workspace="workspace",
    )
    try:
        _write_style_rules(provider, _rules())
        block = provider.system_prompt_block()
        trace = provider.behavior_policy_trace() or {}
        delivery = dict(dict(trace.get("system_prompt_block") or {}).get("active_preference_contract_delivery") or {})
        behavior_rows = provider._store.conn.execute("select count(*) from behavior_contracts").fetchone()[0] if provider._store else -1
        compiled_rows = provider._store.conn.execute("select count(*) from compiled_behavior_policies").fetchone()[0] if provider._store else -1
        return {
            "case_id": "behavior_card_prompt_build",
            "route_class": "system_prompt_behavior_card",
            "semantic_backend_calls": {},
            "semantic_backend_call_total": 0,
            "shelf_backend_calls": {},
            "current_truth_rebuild_calls": 0,
            "profile_like_fallback_count": 0,
            "profile_indexed_lookup_count": 0,
            "packet_token_estimate": 0,
            "packet_selected_tokens": 0,
            "packet_dropped_tokens": 0,
            "packet_budget_status": "not_applicable",
            "protected_truth_drop_attempts": 0,
            "current_truth_row_count": 0,
            "non_answerable_row_count": 0,
            "ordinary_hot_path_rebuild": False,
            "behavior_card_char_count": len(block),
            "behavior_card_rule_count": delivery.get("compiled_rule_count"),
            "behavior_card_delivery_status": delivery.get("delivery_status"),
            "durable_behavior_rows": {
                "behavior_contracts": behavior_rows,
                "compiled_behavior_policies": compiled_rows,
            },
        }
    finally:
        provider.shutdown()


def _workloads(root: Path) -> list[dict[str, Any]]:
    return [
        _run_packet_case(root, case_id="no_memory_minimal", query="", signals={"memory_intent": "none"}),
        _run_packet_case(
            root,
            case_id="profile_only",
            query="structured profile request",
            signals={"profile_slot_targets": ["identity.name"]},
            seed="profile",
        ),
        _run_packet_case(
            root,
            case_id="current_truth_lookup",
            query="structured current truth request",
            signals={"required_evidence_classes": ["current_truth"]},
            seed="current_truth",
        ),
        _run_packet_case(
            root,
            case_id="stale_correction",
            query="structured current truth request",
            signals={"required_evidence_classes": ["current_truth"]},
            seed="stale_correction",
        ),
        _run_behavior_card_prompt_case(root),
        _run_packet_case(
            root,
            case_id="corpus_semantic_supported",
            query="structured deep corpus request",
            signals={"required_evidence_classes": ["temporal_graph", "corpus", "continuity"]},
        ),
        _run_packet_case(
            root,
            case_id="tight_packet_budget",
            query="structured profile request",
            signals={"profile_slot_targets": ["identity.name"]},
            seed="tight_budget",
            packet_budget_max_candidate_tokens=1,
        ),
        _run_scoped_profile_lookup_case(root),
    ]


def _case_issue(case: Mapping[str, Any]) -> list[str]:
    case_id = str(case.get("case_id") or "")
    issues: list[str] = []
    if case.get("protected_truth_drop_attempts") not in {0, None}:
        issues.append("protected_truth_drop_attempt")
    if case.get("current_truth_rebuild_calls") not in {0, None} and case_id in {"current_truth_lookup", "stale_correction"}:
        issues.append("current_truth_rebuild_on_ordinary_read")
    if int(case.get("profile_like_fallback_count") or 0) != 0:
        issues.append("profile_like_fallback_used")
    if case_id in {"no_memory_minimal", "profile_only", "current_truth_lookup", "stale_correction", "tight_packet_budget"}:
        if int(case.get("semantic_backend_call_total") or 0) != 0:
            issues.append("semantic_called_on_hard_gated_route")
    if case_id == "corpus_semantic_supported" and int(case.get("semantic_backend_call_total") or 0) <= 0:
        issues.append("semantic_not_called_on_deep_supported_route")
    if case_id == "no_memory_minimal" and any(int(value or 0) for value in dict(case.get("shelf_backend_calls") or {}).values()):
        issues.append("no_memory_route_called_shelf")
    if case_id == "profile_only":
        calls = dict(case.get("shelf_backend_calls") or {})
        for name in ("search_continuity", "recent_continuity", "search_transcript", "search_graph", "search_corpus"):
            if int(calls.get(name) or 0) != 0:
                issues.append(f"profile_route_called_{name}")
    if case_id == "behavior_card_prompt_build":
        if case.get("behavior_card_rule_count") != 25:
            issues.append("behavior_card_rule_count_mismatch")
        rows = dict(case.get("durable_behavior_rows") or {})
        if int(rows.get("behavior_contracts") or 0) or int(rows.get("compiled_behavior_policies") or 0):
            issues.append("behavior_card_created_durable_behavior_rows")
    if case_id == "scoped_profile_lookup":
        if not case.get("lookup_hit"):
            issues.append("scoped_profile_lookup_miss")
        if int(case.get("profile_indexed_lookup_count") or 0) <= 0:
            issues.append("scoped_profile_index_not_used")
    return issues


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-workload-replay-") as tmp:
        cases = _workloads(Path(tmp))
    failures = {case["case_id"]: _case_issue(case) for case in cases}
    failures = {key: value for key, value in failures.items() if value}
    summary = {
        "case_count": len(cases),
        "total_semantic_backend_calls": sum(int(case.get("semantic_backend_call_total") or 0) for case in cases),
        "hard_gated_semantic_backend_calls": sum(
            int(case.get("semantic_backend_call_total") or 0)
            for case in cases
            if case.get("case_id") in {"no_memory_minimal", "profile_only", "current_truth_lookup", "stale_correction", "tight_packet_budget"}
        ),
        "current_truth_rebuild_calls": sum(int(case.get("current_truth_rebuild_calls") or 0) for case in cases),
        "profile_like_fallback_count": sum(int(case.get("profile_like_fallback_count") or 0) for case in cases),
        "protected_truth_drop_attempts": sum(int(case.get("protected_truth_drop_attempts") or 0) for case in cases),
        "total_packet_token_estimate": sum(int(case.get("packet_token_estimate") or 0) for case in cases),
        "llm_calls_performed": False,
    }
    return {
        "schema": SCHEMA,
        "status": "pass" if not failures else "fail",
        "failure_reasons": [f"{case_id}:{issue}" for case_id, issues in failures.items() for issue in issues],
        "summary": summary,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Brainstack workload performance replay without LLM calls.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "failure_reasons": report["failure_reasons"]}, ensure_ascii=True, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
