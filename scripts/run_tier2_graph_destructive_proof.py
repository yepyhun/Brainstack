#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack import BrainstackMemoryProvider  # noqa: E402

REPORT_SCHEMA = "brainstack.tier2_graph_destructive_proof.v1"
SESSION_ID = "tier2-graph-destructive-proof"
USER_ID = "public-safe-user"
AGENT_ID = "brainstack-verifier"
WORKSPACE_ID = "verification"


def _provider(
    db_path: Path,
    *,
    extractor: Callable[..., dict[str, Any]] | None = None,
    transcript: str = "",
    tier2_runtime: str = "internal_extractor",
) -> BrainstackMemoryProvider:
    config: dict[str, Any] = {
        "db_path": str(db_path),
        "graph_backend": "sqlite",
        "corpus_backend": "sqlite",
        "tier2_runtime": tier2_runtime,
        "tier2_transcript_limit": 4,
        "tier2_timeout_seconds": 2,
        "tier2_hindsight_llm_provider": "hermes_managed",
        "tier2_hindsight_llm_model": "gpt-5.5",
    }
    if extractor is not None:
        config["_tier2_extractor"] = extractor
    provider = BrainstackMemoryProvider(config)
    provider.initialize(
        SESSION_ID,
        platform="verification",
        user_id=USER_ID,
        agent_identity=AGENT_ID,
        agent_workspace=WORKSPACE_ID,
    )
    if transcript:
        assert provider._store is not None
        provider._store.add_transcript_entry(
            session_id=SESSION_ID,
            turn_number=1,
            kind="turn",
            content=transcript,
            source="verification",
            metadata=provider._scoped_metadata(),
        )
    return provider


def _count(provider: BrainstackMemoryProvider, table: str) -> int:
    assert provider._store is not None
    row = provider._store.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"] if row is not None else 0)


def _active_relations(provider: BrainstackMemoryProvider) -> list[dict[str, Any]]:
    assert provider._store is not None
    rows = provider._store.conn.execute(
        """
        SELECT r.id, s.canonical_name AS subject, r.predicate, r.object_text, r.metadata_json
        FROM graph_relations r
        JOIN graph_entities s ON s.id = r.subject_entity_id
        WHERE r.active = 1
        ORDER BY r.id
        """
    ).fetchall()
    output: list[dict[str, Any]] = []
    for row in rows:
        try:
            metadata = json.loads(str(row["metadata_json"] or "{}"))
        except ValueError:
            metadata = {}
        output.append(
            {
                "id": int(row["id"]),
                "subject": str(row["subject"] or ""),
                "predicate": str(row["predicate"] or ""),
                "object": str(row["object_text"] or ""),
                "lineage_status": (metadata.get("graph_source_lineage") or {}).get("status"),
                "decision_truth_eligible": bool((metadata.get("tier2_decision_core") or {}).get("truth_eligible")),
            }
        )
    return output


def _latest_tier2(provider: BrainstackMemoryProvider) -> Mapping[str, Any]:
    doctor = provider.memory_kernel_doctor(strict=True)
    return doctor.get("capabilities", {}).get("tier2", {}) if isinstance(doctor.get("capabilities"), Mapping) else {}


def _graph_producer(provider: BrainstackMemoryProvider) -> Mapping[str, Any]:
    doctor = provider.memory_kernel_doctor(strict=True)
    return doctor.get("capabilities", {}).get("graph_producer", {}) if isinstance(doctor.get("capabilities"), Mapping) else {}


def _record_failed_runs(provider: BrainstackMemoryProvider, *, count: int = 7) -> None:
    assert provider._store is not None
    for index in range(count):
        provider._store.record_tier2_run_result(
            {
                "run_id": f"phase276_4_failed_run_{index}",
                "session_id": SESSION_ID,
                "turn_number": index + 1,
                "trigger_reason": "phase276_4_dirty_fixture",
                "request_status": "failed",
                "json_parse_status": "not_run",
                "status": "failed",
                "transcript_count": 1,
                "extracted_counts": {},
                "action_counts": {},
                "writes_performed": 0,
                "no_op_reasons": [],
                "error_reason": "private provider/auth failure detail must not leak",
                "duration_ms": 1,
            }
        )


def _failed_dirty_probe(tmp: Path) -> dict[str, Any]:
    provider = _provider(tmp / "failed_dirty.sqlite3")
    try:
        _record_failed_runs(provider)
        doctor = provider.memory_kernel_doctor(strict=True)
        stats = json.loads(provider.handle_tool_call("brainstack_stats", {"strict": True}))
        tier2 = doctor.get("capabilities", {}).get("tier2", {})
        graph = doctor.get("capabilities", {}).get("graph", {})
        producer = doctor.get("capabilities", {}).get("graph_producer", {})
        latest = tier2.get("latest_persistent_run", {})
        return {
            "doctor_verdict": doctor.get("verdict"),
            "stats_status": stats.get("status"),
            "tier2_status": tier2.get("status"),
            "tier2_active": tier2.get("active"),
            "tier2_reason_code": tier2.get("reason_code"),
            "latest_run_status": latest.get("status"),
            "latest_request_status": latest.get("request_status"),
            "latest_error_recorded": latest.get("error_recorded"),
            "raw_error_leaked": "error_reason" in latest,
            "graph_status": graph.get("status"),
            "graph_relation_count": _count(provider, "graph_relations"),
            "producer_state": producer.get("producer_state"),
            "producer_reason_code": producer.get("reason_code"),
        }
    finally:
        provider.shutdown()


def _unbound_probe(tmp: Path) -> dict[str, Any]:
    provider = _provider(tmp / "unbound.sqlite3", tier2_runtime="hindsight_public_api_bridge")
    try:
        route = provider.lifecycle_status().get("tier2_runtime_route", {})
        doctor = provider.memory_kernel_doctor(strict=True)
        tier2 = doctor.get("capabilities", {}).get("tier2", {})
        return {
            "route_binding_status": route.get("binding_status"),
            "route_binding_reason_code": route.get("binding_reason_code"),
            "doctor_verdict": doctor.get("verdict"),
            "tier2_status": tier2.get("status"),
            "tier2_active": tier2.get("active"),
            "tier2_reason_code": tier2.get("reason_code"),
        }
    finally:
        provider.shutdown()


def _projected_probe(tmp: Path) -> dict[str, Any]:
    def extractor(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "relations": [
                {
                    "subject": "System Alpha",
                    "predicate": "inspired_by",
                    "object": "Capability Atlas",
                    "source_quote": "System Alpha is inspired by Capability Atlas.",
                    "confidence": 0.97,
                }
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "phase276_4"},
        }

    provider = _provider(
        tmp / "projected.sqlite3",
        extractor=extractor,
        transcript="User: System Alpha is inspired by Capability Atlas.",
    )
    try:
        result = provider._run_tier2_batch(session_id=SESSION_ID, turn_number=1, trigger_reason="phase276_4")
        snapshot = provider._store.get_current_truth_l0_snapshot(limit=100) if provider._store is not None else {}
        return {
            "run_status": result.get("status"),
            "writes_performed": result.get("writes_performed"),
            "action_counts": result.get("action_counts"),
            "relation_count": _count(provider, "graph_relations"),
            "relations": _active_relations(provider),
            "admission_receipts": _count(provider, "admission_receipts"),
            "canonical_memory_events": _count(provider, "canonical_memory_events"),
            "answerable_graph_rows": [
                row.get("event_id")
                for row in snapshot.get("current_truth_rows", [])
                if row.get("memory_kind") in {"graph_relation", "graph_state"} and row.get("answerable_current_truth")
            ],
            "producer_state": _graph_producer(provider).get("producer_state"),
            "producer_reason_code": _graph_producer(provider).get("reason_code"),
        }
    finally:
        provider.shutdown()


def _assistant_rejected_probe(tmp: Path) -> dict[str, Any]:
    def extractor(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "relations": [
                {
                    "subject": "System Alpha",
                    "predicate": "inspired_by",
                    "object": "Capability Atlas",
                    "source_quote": "System Alpha is inspired by Capability Atlas.",
                    "confidence": 0.97,
                    "metadata": {"source_role": "assistant"},
                }
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "phase276_4"},
        }

    provider = _provider(
        tmp / "assistant_rejected.sqlite3",
        extractor=extractor,
        transcript="Assistant: System Alpha is inspired by Capability Atlas.",
    )
    try:
        result = provider._run_tier2_batch(session_id=SESSION_ID, turn_number=1, trigger_reason="phase276_4")
        return {
            "run_status": result.get("status"),
            "writes_performed": result.get("writes_performed"),
            "action_counts": result.get("action_counts"),
            "relation_count": _count(provider, "graph_relations"),
            "admission_receipts": _count(provider, "admission_receipts"),
            "canonical_memory_events": _count(provider, "canonical_memory_events"),
            "producer_state": _graph_producer(provider).get("producer_state"),
            "producer_reason_code": _graph_producer(provider).get("reason_code"),
        }
    finally:
        provider.shutdown()


def _unverified_rejected_probe(tmp: Path) -> dict[str, Any]:
    def extractor(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "relations": [
                {
                    "subject": "System Alpha",
                    "predicate": "inspired_by",
                    "object": "Capability Atlas",
                    "source_quote": "System Alpha is inspired by Capability Atlas.",
                    "confidence": 0.97,
                }
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "phase276_4"},
        }

    provider = _provider(
        tmp / "unverified_rejected.sqlite3",
        extractor=extractor,
        transcript="User: System Alpha and Capability Atlas were mentioned without a durable relation assertion.",
    )
    try:
        result = provider._run_tier2_batch(session_id=SESSION_ID, turn_number=1, trigger_reason="phase276_4")
        snapshot = provider._store.get_current_truth_l0_snapshot(limit=100) if provider._store is not None else {}
        return {
            "run_status": result.get("status"),
            "writes_performed": result.get("writes_performed"),
            "action_counts": result.get("action_counts"),
            "no_op_reasons": result.get("no_op_reasons"),
            "relation_count": _count(provider, "graph_relations"),
            "admission_receipts": _count(provider, "admission_receipts"),
            "canonical_memory_events": _count(provider, "canonical_memory_events"),
            "answerable_graph_rows": [
                row.get("event_id")
                for row in snapshot.get("current_truth_rows", [])
                if row.get("memory_kind") in {"graph_relation", "graph_state"} and row.get("answerable_current_truth")
            ],
            "producer_state": _graph_producer(provider).get("producer_state"),
            "producer_reason_code": _graph_producer(provider).get("reason_code"),
        }
    finally:
        provider.shutdown()


def _case(case_id: str, checks: Mapping[str, bool], payload: Mapping[str, Any]) -> dict[str, Any]:
    failed = sorted(key for key, passed in checks.items() if passed is not True)
    return {
        "case_id": case_id,
        "status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "checks": dict(checks),
        "payload": dict(payload),
    }


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-phase276-4-") as tmpdir:
        tmp = Path(tmpdir)
        failed_dirty = _failed_dirty_probe(tmp)
        unbound = _unbound_probe(tmp)
        projected = _projected_probe(tmp)
        assistant_rejected = _assistant_rejected_probe(tmp)
        unverified_rejected = _unverified_rejected_probe(tmp)

    projected_relation = (projected.get("relations") or [{}])[0] if projected.get("relations") else {}
    cases = [
        _case(
            "failed_tier2_runs_degrade_visibly_with_empty_graph",
            {
                "doctor_fails": failed_dirty.get("doctor_verdict") == "fail",
                "stats_fail": failed_dirty.get("stats_status") == "fail",
                "tier2_degraded": failed_dirty.get("tier2_reason_code") == "TIER2_PERSISTED_RUN_FAILED",
                "tier2_inactive": failed_dirty.get("tier2_active") is False,
                "raw_error_not_leaked": failed_dirty.get("raw_error_leaked") is False,
                "empty_graph_degraded_honestly": failed_dirty.get("graph_status") == "active"
                and failed_dirty.get("producer_reason_code")
                in {"GRAPH_PRODUCER_NO_INPUT", "GRAPH_PRODUCER_BLOCKED_BY_TIER2_FAILURE"},
                "no_graph_rows": failed_dirty.get("graph_relation_count") == 0,
            },
            failed_dirty,
        ),
        _case(
            "configured_unbound_tier2_degrades_visibly",
            {
                "route_configured_unbound": unbound.get("route_binding_status") == "configured_unbound",
                "doctor_fails": unbound.get("doctor_verdict") == "fail",
                "tier2_unavailable": unbound.get("tier2_status") == "unavailable",
                "tier2_reason_code": unbound.get("tier2_reason_code") == "TIER2_RUNTIME_CONFIGURED_UNBOUND",
                "tier2_inactive": unbound.get("tier2_active") is False,
            },
            unbound,
        ),
        _case(
            "source_backed_typed_relation_projects_with_lineage",
            {
                "run_ok": projected.get("run_status") == "ok",
                "one_write": projected.get("writes_performed") == 1,
                "one_relation": projected.get("relation_count") == 1,
                "lineage_active": projected_relation.get("lineage_status") == "active",
                "decision_truth_eligible": projected_relation.get("decision_truth_eligible") is True,
                "receipt_present": int(projected.get("admission_receipts") or 0) > 0,
                "canonical_event_present": int(projected.get("canonical_memory_events") or 0) > 0,
                "answerable_graph_projected": len(projected.get("answerable_graph_rows") or []) == 1,
                "producer_projected": projected.get("producer_reason_code") == "GRAPH_PRODUCER_PROJECTED_TYPED_INPUT",
            },
            projected,
        ),
        _case(
            "assistant_authored_relation_rejected_no_graph_truth",
            {
                "run_ok": assistant_rejected.get("run_status") == "ok",
                "no_writes": assistant_rejected.get("writes_performed") == 0,
                "no_relation": assistant_rejected.get("relation_count") == 0,
                "rejection_visible": assistant_rejected.get("producer_reason_code") == "GRAPH_PRODUCER_TYPED_INPUT_REJECTED",
                "receipt_or_trace_present": int(assistant_rejected.get("admission_receipts") or 0) > 0,
            },
            assistant_rejected,
        ),
        _case(
            "unverified_raw_chat_relation_rejected_no_graph_truth",
            {
                "run_ok": unverified_rejected.get("run_status") == "ok",
                "no_writes": unverified_rejected.get("writes_performed") == 0,
                "no_relation": unverified_rejected.get("relation_count") == 0,
                "no_answerable_graph": unverified_rejected.get("answerable_graph_rows") == [],
                "producer_rejected": unverified_rejected.get("producer_reason_code")
                in {"GRAPH_PRODUCER_TYPED_INPUT_REJECTED", "GRAPH_PRODUCER_NO_INPUT"},
            },
            unverified_rejected,
        ),
    ]
    failures = [case for case in cases if case["status"] != "pass"]
    proof = {
        "dirty_live_shaped_failed_runs": cases[0]["status"] == "pass",
        "configured_unbound_not_healthy": cases[1]["status"] == "pass",
        "empty_graph_explains_no_input_or_failed_dependency": failed_dirty.get("producer_reason_code")
        in {"GRAPH_PRODUCER_NO_INPUT", "GRAPH_PRODUCER_BLOCKED_BY_TIER2_FAILURE"},
        "source_backed_relation_requires_lineage_receipt_event": cases[2]["status"] == "pass",
        "assistant_candidate_no_graph_truth": cases[3]["status"] == "pass",
        "unverified_raw_chat_candidate_no_graph_truth": cases[4]["status"] == "pass",
        "failed_run_raw_error_not_agent_facing": failed_dirty.get("raw_error_leaked") is False,
        "no_enabled_means_healthy": failed_dirty.get("doctor_verdict") == "fail" and unbound.get("doctor_verdict") == "fail",
    }
    issues = [key for key, value in proof.items() if value is not True] + [case["case_id"] for case in failures]
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "llm_calls_performed": False,
        "issue_count": len(issues),
        "issues": issues,
        "proof": proof,
        "case_count": len(cases),
        "failure_case_ids": [case["case_id"] for case in failures],
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("schema", "status", "case_count", "issue_count", "issues")}, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
