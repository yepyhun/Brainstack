#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack import BrainstackMemoryProvider  # noqa: E402


def _provider(db_path: Path, extractor: Any, *, transcript: str) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(db_path),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "tier2_transcript_limit": 4,
            "tier2_timeout_seconds": 2,
            "_tier2_extractor": extractor,
        }
    )
    provider.initialize(
        "typed-graph-producer-verifier",
        platform="verification",
        user_id="public-safe-user",
        agent_identity="brainstack-verifier",
        agent_workspace="verification",
    )
    assert provider._store is not None
    provider._store.add_transcript_entry(
        session_id="typed-graph-producer-verifier",
        turn_number=1,
        kind="turn",
        content=transcript,
        source="verification",
        metadata=provider._scoped_metadata(),
    )
    return provider


def _relation_count(provider: BrainstackMemoryProvider) -> int:
    assert provider._store is not None
    row = provider._store.conn.execute(
        "SELECT COUNT(*) AS count FROM graph_relations WHERE active = 1"
    ).fetchone()
    return int(row["count"] if row is not None else 0)


def _relation_metadata(provider: BrainstackMemoryProvider) -> dict[str, Any]:
    assert provider._store is not None
    row = provider._store.conn.execute(
        "SELECT metadata_json FROM graph_relations WHERE active = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    if row is None:
        return {}
    try:
        payload = json.loads(str(row["metadata_json"] or "{}"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


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
                    "metadata": {"source_role": "user"},
                }
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "verifier"},
        }

    provider = _provider(
        tmp / "projected.sqlite3",
        extractor,
        transcript="User: System Alpha is inspired by Capability Atlas.",
    )
    try:
        result = provider._run_tier2_batch(
            session_id="typed-graph-producer-verifier",
            turn_number=1,
            trigger_reason="typed_graph_verifier",
        )
        doctor = provider.memory_kernel_doctor(strict=True)
        graph_producer = doctor.get("capabilities", {}).get("graph_producer", {})
        relation_metadata = _relation_metadata(provider)
        admission = relation_metadata.get("admission") if isinstance(relation_metadata.get("admission"), dict) else {}
        lineage = (
            relation_metadata.get("graph_source_lineage")
            if isinstance(relation_metadata.get("graph_source_lineage"), dict)
            else {}
        )
        tier2_decision_core = (
            relation_metadata.get("tier2_decision_core")
            if isinstance(relation_metadata.get("tier2_decision_core"), dict)
            else {}
        )
        return {
            "status": result.get("status"),
            "writes_performed": result.get("writes_performed"),
            "action_counts": result.get("action_counts"),
            "relation_count": _relation_count(provider),
            "doctor_verdict": doctor.get("verdict"),
            "producer_state": graph_producer.get("producer_state"),
            "producer_reason_code": graph_producer.get("reason_code"),
            "public_safe": bool(graph_producer.get("public_safe")),
            "admission_decision": admission.get("decision"),
            "admission_truth_eligible": admission.get("truth_eligible"),
            "admission_source_event_present": bool(str(admission.get("source_event_id") or "").strip()),
            "lineage_status": lineage.get("status"),
            "lineage_source_kind": lineage.get("source_kind"),
            "tier2_core_truth_eligible": tier2_decision_core.get("truth_eligible"),
        }
    finally:
        provider.shutdown()


def _rejected_probe(tmp: Path) -> dict[str, Any]:
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
            "_meta": {"json_parse_status": "ok", "parse_context": "verifier"},
        }

    provider = _provider(
        tmp / "rejected.sqlite3",
        extractor,
        transcript="Assistant: System Alpha is inspired by Capability Atlas.",
    )
    try:
        result = provider._run_tier2_batch(
            session_id="typed-graph-producer-verifier",
            turn_number=1,
            trigger_reason="typed_graph_verifier",
        )
        doctor = provider.memory_kernel_doctor(strict=True)
        graph_producer = doctor.get("capabilities", {}).get("graph_producer", {})
        return {
            "status": result.get("status"),
            "writes_performed": result.get("writes_performed"),
            "action_counts": result.get("action_counts"),
            "relation_count": _relation_count(provider),
            "doctor_verdict": doctor.get("verdict"),
            "producer_state": graph_producer.get("producer_state"),
            "producer_reason_code": graph_producer.get("reason_code"),
            "public_safe": bool(graph_producer.get("public_safe")),
        }
    finally:
        provider.shutdown()


def _empty_probe(tmp: Path) -> dict[str, Any]:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp / "empty.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "typed-graph-producer-verifier",
        platform="verification",
        user_id="public-safe-user",
        agent_identity="brainstack-verifier",
        agent_workspace="verification",
    )
    try:
        doctor = provider.memory_kernel_doctor(strict=True)
        graph = doctor.get("capabilities", {}).get("graph", {})
        graph_producer = doctor.get("capabilities", {}).get("graph_producer", {})
        return {
            "doctor_verdict": doctor.get("verdict"),
            "graph_status": graph.get("status"),
            "graph_producer_requested": graph_producer.get("requested"),
            "producer_state": graph_producer.get("producer_state"),
            "producer_reason_code": graph_producer.get("reason_code"),
            "relation_count": _relation_count(provider),
        }
    finally:
        provider.shutdown()


def _raw_chat_probe(tmp: Path) -> dict[str, Any]:
    def extractor(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "profile_items": [],
            "states": [],
            "relations": [],
            "inferred_relations": [],
            "typed_entities": [],
            "temporal_events": [],
            "decisions": [],
            "continuity_summary": "",
            "_meta": {"json_parse_status": "ok", "parse_context": "raw_chat_verifier"},
        }

    provider = _provider(
        tmp / "raw_chat.sqlite3",
        extractor,
        transcript="User: System Alpha is inspired by Capability Atlas.",
    )
    try:
        result = provider._run_tier2_batch(
            session_id="typed-graph-producer-verifier",
            turn_number=1,
            trigger_reason="typed_graph_raw_chat_verifier",
        )
        doctor = provider.memory_kernel_doctor(strict=True)
        graph_producer = doctor.get("capabilities", {}).get("graph_producer", {})
        return {
            "status": result.get("status"),
            "writes_performed": result.get("writes_performed"),
            "action_counts": result.get("action_counts"),
            "relation_count": _relation_count(provider),
            "doctor_verdict": doctor.get("verdict"),
            "producer_state": graph_producer.get("producer_state"),
            "producer_reason_code": graph_producer.get("reason_code"),
            "latest_graph_candidate_counts": graph_producer.get("latest_graph_candidate_counts"),
        }
    finally:
        provider.shutdown()


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-typed-graph-") as tmpdir:
        tmp = Path(tmpdir)
        projected = _projected_probe(tmp)
        rejected = _rejected_probe(tmp)
        empty = _empty_probe(tmp)
        raw_chat = _raw_chat_probe(tmp)

    issues: list[str] = []
    if projected.get("status") != "ok" or projected.get("relation_count") != 1:
        issues.append("projected_relation_missing")
    if projected.get("producer_state") != "projected":
        issues.append("projected_state_missing")
    if projected.get("public_safe") is not True:
        issues.append("projected_status_not_public_safe")
    if projected.get("admission_decision") != "ACCEPT_DURABLE":
        issues.append("projected_admission_missing")
    if projected.get("admission_truth_eligible") is not True:
        issues.append("projected_admission_not_truth_eligible")
    if projected.get("admission_source_event_present") is not True:
        issues.append("projected_source_event_missing")
    if projected.get("lineage_status") != "active":
        issues.append("projected_lineage_missing")
    if projected.get("tier2_core_truth_eligible") is not True:
        issues.append("projected_tier2_core_not_truth_eligible")
    if rejected.get("relation_count") != 0:
        issues.append("rejected_relation_created_graph_row")
    if rejected.get("producer_state") != "rejected":
        issues.append("rejected_state_missing")
    if empty.get("graph_status") != "active":
        issues.append("empty_graph_backend_not_active")
    if empty.get("producer_state") != "no_input":
        issues.append("empty_graph_not_reported_as_no_input")
    if raw_chat.get("status") != "ok" or raw_chat.get("relation_count") != 0:
        issues.append("raw_chat_created_graph_relation")
    if raw_chat.get("producer_state") != "no_graph_candidates":
        issues.append("raw_chat_not_reported_as_no_graph_candidates")

    return {
        "schema": "brainstack.typed_graph_producer_population.v1",
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "issues": issues,
        "projected_probe": projected,
        "rejected_probe": rejected,
        "empty_probe": empty,
        "raw_chat_probe": raw_chat,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify typed graph producer population.")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
