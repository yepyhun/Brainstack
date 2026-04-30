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

from brainstack.multihop_readiness import build_multihop_readiness_projection  # noqa: E402


def _event(
    *,
    event_id: str,
    subject_ref: str,
    predicate: str,
    object_ref: str,
    event_type: str = "durable_fact_committed",
    truth_eligible: bool = True,
    support_visibility: str = "answer_evidence",
    valid_to: str = "",
) -> dict[str, Any]:
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
            "principal_scope_key": "principal:a",
            "workspace_scope_key": "workspace:a",
            "session_id": "session:a",
        },
        "claim": {
            "memory_kind": "graph_relation",
            "target_slot": predicate,
            "subject_ref": subject_ref,
            "predicate": predicate,
            "object_ref": object_ref,
            "normalized_value_hash": f"sha256:value_{event_id}",
            "stable_fact_id": f"{subject_ref}:{predicate}:{object_ref}",
        },
        "authority": {
            "authority_class": "user_explicit" if truth_eligible else "support_only",
            "truth_eligible": truth_eligible,
            "support_visibility": support_visibility,
            "confidence": 0.95,
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
            "entity_refs": [subject_ref, object_ref],
            "relation_refs": [f"rel:{event_id}"],
            "budget_class": "task_relevant",
            "authority_critical": truth_eligible,
            "projection_hints": {"graph_ready": True, "budget_ready": True, "multihop_ready": True},
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
        _event(event_id="edge_component_dependency", subject_ref="entity:component:a", predicate="depends_on", object_ref="entity:component:b"),
        _event(event_id="edge_dependency_owner", subject_ref="entity:component:b", predicate="owned_by", object_ref="entity:team:c"),
        _event(
            event_id="expired_prior_owner",
            subject_ref="entity:component:b",
            predicate="owned_by",
            object_ref="entity:team:old",
            valid_to="2026-04-30T12:00:00Z",
        ),
        _event(
            event_id="support_uncertain_relation",
            subject_ref="entity:component:a",
            predicate="maybe_related_to",
            object_ref="entity:topic:x",
            event_type="support_event",
            truth_eligible=False,
            support_visibility="normal",
        ),
        _event(
            event_id="conflict_created_by",
            subject_ref="entity:project:demo",
            predicate="created_by",
            object_ref="entity:user:conflict",
            event_type="conflict_opened",
            truth_eligible=False,
            support_visibility="contradiction_only",
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    projection = build_multihop_readiness_projection(fixture_events())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": projection["status"],
                "traversal_edge_count": len(projection["traversal_edges"]),
                "blocked_edge_count": len(projection["blocked_edges"]),
                "critical_counters": projection["critical_counters"],
            },
            sort_keys=True,
        )
    )
    return 0 if projection["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
