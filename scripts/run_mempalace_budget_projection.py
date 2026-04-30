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

from brainstack.mempalace_budget_projection import project_canonical_events_to_mempalace_budget  # noqa: E402


def _event(
    *,
    event_id: str,
    memory_kind: str,
    budget_class: str,
    truth_eligible: bool,
    support_visibility: str,
    authority_critical: bool = False,
) -> dict[str, Any]:
    return {
        "event": {
            "event_id": event_id,
            "schema_version": "brainstack.canonical_memory_event.v1",
            "event_type": "durable_fact_committed" if truth_eligible else "support_event",
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
            "memory_kind": memory_kind,
            "target_slot": f"{memory_kind}.slot",
            "subject_ref": "entity:subject",
            "predicate": "related_to",
            "object_ref": "entity:object",
            "normalized_value_hash": f"sha256:value_{event_id}",
            "stable_fact_id": f"{memory_kind}:{event_id}",
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
            "valid_to": "",
            "transaction_time": "2026-04-30T10:00:01Z",
            "supersedes": [],
            "superseded_by": "",
        },
        "projection": {
            "entity_refs": [],
            "relation_refs": [],
            "budget_class": budget_class,
            "authority_critical": authority_critical,
            "projection_hints": {
                "graph_ready": memory_kind == "graph_relation",
                "budget_ready": True,
                "multihop_ready": memory_kind == "graph_relation",
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
    events = [
        _event(
            event_id="identity_rule",
            memory_kind="preference",
            budget_class="always_active",
            truth_eligible=True,
            support_visibility="answer_evidence",
            authority_critical=True,
        ),
        _event(
            event_id="project_creator",
            memory_kind="project",
            budget_class="active_if_task_relevant",
            truth_eligible=True,
            support_visibility="answer_evidence",
            authority_critical=True,
        ),
        _event(
            event_id="reference_url",
            memory_kind="reference",
            budget_class="retrieval_only",
            truth_eligible=True,
            support_visibility="inspect_only",
        ),
    ]
    events.extend(
        _event(
            event_id=f"support_noise_{index}",
            memory_kind="support_only",
            budget_class="support_only",
            truth_eligible=False,
            support_visibility="normal",
        )
        for index in range(16)
    )
    return events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-active-tokens", type=int, default=42)
    args = parser.parse_args()

    projection = project_canonical_events_to_mempalace_budget(
        fixture_events(),
        max_active_tokens=args.max_active_tokens,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": projection["status"],
                "selected_active_tokens": projection["selected_active_tokens"],
                "baseline_tokens": projection["baseline_tokens"],
                "estimated_delta_tokens": projection["estimated_delta_tokens"],
                "critical_counters": projection["critical_counters"],
            },
            sort_keys=True,
        )
    )
    return 0 if projection["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
