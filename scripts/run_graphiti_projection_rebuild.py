#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.graphiti_projection import project_canonical_events_to_graphiti  # noqa: E402


def _base_event(
    *,
    event_id: str,
    memory_kind: str = "graph_relation",
    event_type: str = "durable_fact_committed",
    truth_eligible: bool = True,
    support_visibility: str = "answer_evidence",
    valid_to: str = "",
    principal_scope_key: str = "principal:a",
) -> dict[str, Any]:
    graph_ready = memory_kind == "graph_relation"
    return {
        "event": {
            "event_id": event_id,
            "schema_version": "brainstack.canonical_memory_event.v1",
            "event_type": event_type,
            "idempotency_key": f"sha256:{event_id}",
        },
        "source": {
            "source_event_id": f"evt_{event_id}",
            "source_span_id": f"span_{event_id}",
            "source_quote_hash": f"sha256:quote_{event_id}",
            "speaker": "user",
            "assertion_speaker": "user",
            "source_modality": "conversation",
            "observed_at": "2026-04-30T10:00:00Z",
        },
        "scope": {
            "tenant_id": "local",
            "principal_scope_key": principal_scope_key,
            "workspace_scope_key": "workspace:a",
            "session_id": "session:a",
        },
        "claim": {
            "memory_kind": memory_kind,
            "target_slot": "project.created_by",
            "subject_ref": "entity:project:demo",
            "predicate": "created_by",
            "object_ref": "entity:user:creator",
            "normalized_value_hash": "sha256:value",
            "stable_fact_id": "project:demo:created_by",
        },
        "authority": {
            "authority_class": "user_explicit" if truth_eligible else "support_only",
            "truth_eligible": truth_eligible,
            "support_visibility": support_visibility,
            "confidence": 0.99,
            "admission_decision_id": f"adm_{event_id}",
            "receipt_id": "1" if truth_eligible else "",
        },
        "temporal": {
            "valid_from": "2026-04-30T10:00:00Z",
            "valid_to": valid_to,
            "transaction_time": "2026-04-30T10:00:01Z",
            "supersedes": [],
            "superseded_by": "",
        },
        "projection": {
            "entity_refs": ["entity:project:demo", "entity:user:creator"],
            "relation_refs": ["rel:demo:created_by:creator"] if graph_ready else [],
            "budget_class": "task_relevant" if truth_eligible else "archived",
            "authority_critical": truth_eligible,
            "projection_hints": {
                "graph_ready": graph_ready,
                "budget_ready": True,
                "multihop_ready": graph_ready,
            },
        },
        "trace": {
            "proposal_id": f"proposal_{event_id}",
            "donor_trace": {"donor": "hindsight", "donor_version": "test"},
            "policy_versions": {"admission": "test", "slot_registry": "test"},
        },
        "extensions": {},
    }


def fixture_events() -> list[dict[str, Any]]:
    return [
        _base_event(event_id="current_graph_fact"),
        _base_event(event_id="expired_graph_fact", valid_to="2026-04-30T12:00:00Z"),
        _base_event(
            event_id="inspect_only_graph_fact",
            event_type="proposal_rejected",
            truth_eligible=False,
            support_visibility="inspect_only",
        ),
        _base_event(
            event_id="conflict_graph_fact",
            event_type="conflict_opened",
            truth_eligible=False,
            support_visibility="contradiction_only",
        ),
        _base_event(event_id="preference_not_graph", memory_kind="preference"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    projection = project_canonical_events_to_graphiti(fixture_events())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": projection["status"], "critical_counters": projection["critical_counters"]}, sort_keys=True))
    return 0 if projection["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
