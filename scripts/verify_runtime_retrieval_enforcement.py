#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.retrieval_pipeline.channel_collection import collect_semantic_rows  # noqa: E402
from brainstack.retrieval_channel_deadlines import build_channel_deadline_statuses  # noqa: E402


PRINCIPAL_SCOPE = "principal:runtime-retrieval-enforcement"


class RuntimeRetrievalSpyStore(BrainstackStore):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.reset_runtime_spies()

    def reset_runtime_spies(self) -> None:
        self.calls: dict[str, int] = {
            "search_semantic_evidence": 0,
            "search_conversation_semantic": 0,
            "search_corpus_semantic": 0,
            "search_corpus_semantic_with_status": 0,
            "search_graph": 0,
            "search_corpus": 0,
            "get_current_truth_l0_candidates": 0,
            "get_current_truth_l0_snapshot": 0,
            "list_canonical_memory_events": 0,
        }
        self.semantic_kwargs: list[dict[str, Any]] = []

    def search_semantic_evidence(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls["search_semantic_evidence"] += 1
        self.semantic_kwargs.append(dict(kwargs))
        return super().search_semantic_evidence(*args, **kwargs)

    def search_conversation_semantic(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls["search_conversation_semantic"] += 1
        return super().search_conversation_semantic(*args, **kwargs)

    def search_corpus_semantic(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls["search_corpus_semantic"] += 1
        return super().search_corpus_semantic(*args, **kwargs)

    def search_corpus_semantic_with_status(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls["search_corpus_semantic_with_status"] += 1
        return super().search_corpus_semantic_with_status(*args, **kwargs)

    def search_graph(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls["search_graph"] += 1
        return super().search_graph(*args, **kwargs)

    def search_corpus(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls["search_corpus"] += 1
        return super().search_corpus(*args, **kwargs)

    def get_current_truth_l0_candidates(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls["get_current_truth_l0_candidates"] += 1
        return super().get_current_truth_l0_candidates(*args, **kwargs)

    def get_current_truth_l0_snapshot(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls["get_current_truth_l0_snapshot"] += 1
        return super().get_current_truth_l0_snapshot(*args, **kwargs)

    def list_canonical_memory_events(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls["list_canonical_memory_events"] += 1
        return super().list_canonical_memory_events(*args, **kwargs)


class _UnsupportedExternalBackend:
    def close(self) -> None:
        return None


class _TimeoutCorpusBackend:
    target_name = "timeout-corpus-backend"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search_semantic(self, *, query: str, limit: int, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        self.calls.append({"query": query, "limit": limit, "where": dict(where or {})})
        raise TimeoutError("runtime retrieval timeout containment probe")

    def close(self) -> None:
        return None


def _event() -> dict[str, Any]:
    return {
        "event": {
            "event_id": "runtime_retrieval_current_1",
            "schema_version": "brainstack.canonical_memory_event.v1",
            "event_type": "durable_fact_committed",
            "idempotency_key": "sha256:runtime_retrieval_current_1",
        },
        "source": {
            "source_event_id": "source_runtime_retrieval_current_1",
            "source_span_id": "span_runtime_retrieval_current_1",
            "source_quote_hash": "sha256:runtime_retrieval_quote",
            "speaker": "user",
            "assertion_speaker": "user",
            "source_modality": "conversation",
            "observed_at": "2026-05-03T11:58:59Z",
        },
        "scope": {
            "tenant_id": "local",
            "principal_scope_key": PRINCIPAL_SCOPE,
            "workspace_scope_key": "workspace:runtime-retrieval",
            "session_id": "session:runtime-retrieval",
        },
        "claim": {
            "memory_kind": "profile",
            "target_slot": "profile.preferred_language",
            "subject_ref": "entity:user:runtime-retrieval",
            "predicate": "prefers_language",
            "object_ref": "entity:language:example",
            "normalized_value_hash": "sha256:runtime_retrieval_value",
            "stable_fact_id": "profile:preferred_language",
        },
        "authority": {
            "authority_class": "user_explicit",
            "truth_eligible": True,
            "support_visibility": "answer_evidence",
            "confidence": 0.99,
            "admission_decision_id": "admission_runtime_retrieval_current_1",
            "receipt_id": "receipt_runtime_retrieval_current_1",
        },
        "temporal": {
            "valid_from": "2026-05-03T11:58:00Z",
            "valid_to": "",
            "transaction_time": "2026-05-03T11:59:00Z",
            "supersedes": [],
            "superseded_by": "",
        },
        "projection": {
            "entity_refs": ["entity:user:runtime-retrieval"],
            "relation_refs": ["rel:runtime-retrieval"],
            "budget_class": "task_relevant",
            "authority_critical": True,
            "projection_hints": {"graph_ready": False, "budget_ready": True, "multihop_ready": False},
        },
        "trace": {
            "proposal_id": "proposal_runtime_retrieval_current_1",
            "donor_trace": {"donor": "hindsight", "donor_version": "test"},
            "policy_versions": {"admission": "test", "slot_registry": "test"},
        },
        "extensions": {},
    }


def _packet(store: RuntimeRetrievalSpyStore, query: str, **signals: object) -> dict[str, Any]:
    return build_working_memory_packet(
        store,
        query=query,
        session_id="session:runtime-retrieval-enforcement",
        principal_scope_key=PRINCIPAL_SCOPE,
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
        adaptive_route_signals=dict(signals),
    )


def _plan_id_surface_ok(packet: dict[str, Any]) -> bool:
    plan_id = str(packet.get("retrieval_control_plan", {}).get("plan_id") or "")
    if not plan_id:
        return False
    if packet.get("adaptive_route_plan", {}).get("plan_id") != plan_id:
        return False
    if packet.get("policy", {}).get("adaptive_route_plan", {}).get("plan_id") != plan_id:
        return False
    if packet.get("policy", {}).get("retrieval_control_plan", {}).get("plan_id") != plan_id:
        return False
    if packet.get("retrieval_context_envelope", {}).get("plan_id") != plan_id:
        return False
    return {str(channel.get("plan_id") or "") for channel in packet.get("channels") or []} == {plan_id}


def _deadline_surface_ok(packet: dict[str, Any]) -> bool:
    allowed_support = {"skipped_by_plan", "bounded_sync", "cancellation_unsupported"}
    for channel in packet.get("channels") or []:
        if not isinstance(channel, dict):
            return False
        if str(channel.get("deadline_support_status") or "") not in allowed_support:
            return False
        if not str(channel.get("deadline_enforcement") or ""):
            return False
        if "deadline_ms" not in channel:
            return False
    return True


def _unsupported_deadline_contract(store: RuntimeRetrievalSpyStore, plan: dict[str, Any]) -> dict[str, Any]:
    original_corpus = getattr(store, "_corpus_backend", None)
    original_graph = getattr(store, "_graph_backend", None)
    try:
        store._corpus_backend = _UnsupportedExternalBackend()
        store._graph_backend = _UnsupportedExternalBackend()
        statuses = build_channel_deadline_statuses(store, retrieval_control_plan=plan)
    finally:
        store._corpus_backend = original_corpus
        store._graph_backend = original_graph
    unsupported = [
        name
        for name, status in statuses.items()
        if status.get("support_status") == "cancellation_unsupported"
    ]
    return {"statuses": statuses, "unsupported_paths": unsupported}


def _corpus_semantic_timeout_contract(store: RuntimeRetrievalSpyStore) -> dict[str, Any]:
    original_corpus = getattr(store, "_corpus_backend", None)
    direct_backend = _TimeoutCorpusBackend()
    try:
        store._corpus_backend = direct_backend
        direct = store.search_corpus_semantic_with_status(
            query="timeout containment direct probe",
            limit=4,
            principal_scope_key=PRINCIPAL_SCOPE,
        )
        direct_channel_status = store.corpus_semantic_channel_status()
    finally:
        store._corpus_backend = original_corpus

    pipeline_backend = _TimeoutCorpusBackend()
    try:
        store._corpus_backend = pipeline_backend
        store.reset_runtime_spies()
        channels = collect_semantic_rows(
            store,
            query="timeout containment pipeline probe",
            session_id="session:runtime-retrieval-enforcement",
            principal_scope_key=PRINCIPAL_SCOPE,
            search_queries=["first variant", "second variant", "third variant"],
            transcript_limit=0,
            corpus_limit=2,
            evidence_item_budget=1,
            entity_resolution={},
            semantic_evidence_enabled=True,
            semantic_allowed_shelves=("corpus",),
            semantic_plan_enforced=True,
        )
        pipeline_channel_status = store.corpus_semantic_channel_status()
    finally:
        store._corpus_backend = original_corpus

    direct_calls = list(direct_backend.calls)
    pipeline_calls = list(pipeline_backend.calls)
    direct_no_base_fallback = len(direct_calls) == 1 and direct_calls[0].get("where") != {"semantic_class": "corpus"}
    pipeline_stopped_variants = len(pipeline_calls) == 1
    return {
        "direct_status": str(direct.get("status") or ""),
        "direct_error_kind": str(direct.get("error_kind") or ""),
        "direct_fallback_used": bool(direct.get("fallback_used")),
        "direct_followup_skipped": int(direct.get("followup_skipped") or 0),
        "direct_no_base_fallback": direct_no_base_fallback,
        "direct_backend_call_count": len(direct_calls),
        "pipeline_backend_call_count": len(pipeline_calls),
        "pipeline_stopped_variants": pipeline_stopped_variants,
        "pipeline_rows": len(channels.get("corpus") or []),
        "agent_facing_status": str(pipeline_channel_status.get("status") or direct_channel_status.get("status") or ""),
        "agent_facing_error_kind": str(pipeline_channel_status.get("error_kind") or direct_channel_status.get("error_kind") or ""),
        "agent_facing_followup_skipped": int(
            pipeline_channel_status.get("followup_skipped")
            or direct_channel_status.get("followup_skipped")
            or 0
        ),
    }


def run_probe() -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="brainstack-runtime-retrieval-") as temp:
        store = RuntimeRetrievalSpyStore(str(Path(temp) / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        try:
            store.record_canonical_memory_event(_event())

            store.reset_runtime_spies()
            no_memory = _packet(store, "", memory_intent="none")
            if no_memory["adaptive_route_plan"]["route_class"] != "no_memory_minimal":
                issues.append({"code": "no_memory_route_wrong"})
            if any(store.calls[name] for name in ("search_semantic_evidence", "search_conversation_semantic", "search_corpus_semantic", "search_graph", "search_corpus")):
                issues.append({"code": "no_memory_heavy_backend_call", "calls": dict(store.calls)})

            store.reset_runtime_spies()
            corpus = _packet(store, "structured corpus request", required_evidence_classes=["corpus"])
            corpus_semantic_kwargs = store.semantic_kwargs[-1] if store.semantic_kwargs else {}
            if corpus["adaptive_route_plan"]["route_class"] != "corpus":
                issues.append({"code": "corpus_route_wrong"})
            if tuple(corpus_semantic_kwargs.get("shelves") or ()) != ("corpus",):
                issues.append({"code": "corpus_semantic_not_shelf_scoped", "kwargs": corpus_semantic_kwargs})
            if store.calls["search_graph"] != 0:
                issues.append({"code": "corpus_route_graph_call", "calls": dict(store.calls)})
            if not _plan_id_surface_ok(corpus):
                issues.append({"code": "plan_id_surface_mismatch"})
            if not _deadline_surface_ok(corpus):
                issues.append({"code": "deadline_surface_missing_or_invalid", "channels": corpus.get("channels")})

            store.reset_runtime_spies()
            temporal = _packet(store, "structured temporal graph request", required_evidence_classes=["temporal_graph"])
            temporal_semantic_kwargs = store.semantic_kwargs[-1] if store.semantic_kwargs else {}
            if "corpus" in tuple(temporal_semantic_kwargs.get("shelves") or ()):
                issues.append({"code": "temporal_graph_fetched_corpus_semantic", "kwargs": temporal_semantic_kwargs})
            if store.calls["search_corpus_semantic"] != 0 or store.calls["search_corpus_semantic_with_status"] != 0 or store.calls["search_corpus"] != 0:
                issues.append({"code": "temporal_graph_corpus_call", "calls": dict(store.calls)})
            if not _deadline_surface_ok(temporal):
                issues.append({"code": "temporal_deadline_surface_missing_or_invalid", "channels": temporal.get("channels")})

            store.reset_runtime_spies()
            current = _packet(
                store,
                "structured current truth request",
                required_evidence_classes=["current_truth"],
                current_truth_target_slots=["profile.preferred_language"],
            )
            if current["current_truth_view"]["rebuild"]["source"] != "current_truth_l0_targeted":
                issues.append({"code": "current_truth_not_targeted_l0", "source": current["current_truth_view"]["rebuild"]["source"]})
            if store.calls["get_current_truth_l0_candidates"] != 1:
                issues.append({"code": "targeted_l0_not_called", "calls": dict(store.calls)})
            if store.calls["get_current_truth_l0_snapshot"] != 0 or store.calls["list_canonical_memory_events"] != 0:
                issues.append({"code": "current_truth_broad_or_rebuild_call", "calls": dict(store.calls)})

            combined = json.dumps(
                {
                    "no_memory": no_memory.get("retrieval_context_envelope"),
                    "corpus": corpus.get("retrieval_context_envelope"),
                    "temporal": temporal.get("retrieval_context_envelope"),
                    "current": current.get("retrieval_context_envelope"),
                },
                ensure_ascii=True,
                sort_keys=True,
            )
            if PRINCIPAL_SCOPE in combined:
                issues.append({"code": "raw_scope_leak"})

            unsupported_contract = _unsupported_deadline_contract(store, corpus.get("retrieval_control_plan") or {})
            unsupported_paths = unsupported_contract["unsupported_paths"]
            if "semantic" not in unsupported_paths:
                issues.append({"code": "external_corpus_semantic_not_marked_unsupported", "paths": unsupported_paths})
            if "graph" in unsupported_paths:
                issues.append({"code": "corpus_route_unexpected_graph_deadline_unsupported", "paths": unsupported_paths})

            timeout_contract = _corpus_semantic_timeout_contract(store)
            if timeout_contract["direct_status"] != "degraded":
                issues.append({"code": "corpus_semantic_timeout_not_degraded", "contract": timeout_contract})
            if timeout_contract["direct_error_kind"] != "timeout":
                issues.append({"code": "corpus_semantic_timeout_kind_missing", "contract": timeout_contract})
            if timeout_contract["direct_fallback_used"] is not False or timeout_contract["direct_no_base_fallback"] is not True:
                issues.append({"code": "corpus_semantic_timeout_fell_back_to_base", "contract": timeout_contract})
            if timeout_contract["pipeline_stopped_variants"] is not True:
                issues.append({"code": "corpus_semantic_timeout_retried_variants", "contract": timeout_contract})
            if timeout_contract["agent_facing_status"] != "degraded" or timeout_contract["agent_facing_error_kind"] != "timeout":
                issues.append({"code": "corpus_semantic_timeout_not_agent_facing", "contract": timeout_contract})

            return {
                "schema": "brainstack.runtime_retrieval_enforcement_verifier.v1",
                "status": "pass" if not issues else "fail",
                "issues": issues,
                "public_safe": True,
                "no_memory_route": no_memory["adaptive_route_plan"]["route_class"],
                "corpus_route": corpus["adaptive_route_plan"]["route_class"],
                "corpus_semantic_shelves": list(corpus_semantic_kwargs.get("shelves") or []),
                "temporal_semantic_shelves": list(temporal_semantic_kwargs.get("shelves") or []),
                "current_truth_source": current["current_truth_view"]["rebuild"]["source"],
                "plan_id_surface_ok": _plan_id_surface_ok(corpus),
                "deadline_surface_ok": _deadline_surface_ok(corpus) and _deadline_surface_ok(temporal),
                "timeout_enforcement": "explicit_deadline_support_contract",
                "unsupported_cancellation_paths": unsupported_paths,
                "semantic_timeout_containment": "status_aware_fail_closed",
                "semantic_timeout_no_base_fallback": timeout_contract["direct_no_base_fallback"],
                "semantic_timeout_pipeline_stopped_variants": timeout_contract["pipeline_stopped_variants"],
                "semantic_timeout_followup_skipped": timeout_contract["agent_facing_followup_skipped"],
                "semantic_timeout_agent_facing_status": timeout_contract["agent_facing_status"],
                "semantic_timeout_agent_facing_error_kind": timeout_contract["agent_facing_error_kind"],
            }
        finally:
            store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Brainstack runtime retrieval enforcement spine.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_probe()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    else:
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if report.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
