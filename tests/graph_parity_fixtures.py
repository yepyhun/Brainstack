from __future__ import annotations

from typing import Any

from brainstack.db import BrainstackStore


PRINCIPAL_SCOPE = "principal:graph-parity-fixture"


def seed_graph_parity_fixture(store: BrainstackStore) -> dict[str, Any]:
    """Seed the shared 91-93 graph parity pack."""
    metadata = {"principal_scope_key": PRINCIPAL_SCOPE}
    store.upsert_graph_state(
        subject_name="ExpiredWindowAlpha",
        attribute="availability",
        value_text="active",
        source="graph-parity-fixture",
        metadata={
            **metadata,
            "temporal": {
                "observed_at": "2000-01-01T10:00:00+00:00",
                "valid_from": "2000-01-01T10:00:00+00:00",
                "valid_to": "2000-01-01T12:00:00+00:00",
            },
        },
    )
    store.upsert_graph_state(
        subject_name="CurrentWindowBeta",
        attribute="availability",
        value_text="active",
        source="graph-parity-fixture",
        metadata={
            **metadata,
            "temporal": {
                "observed_at": "2026-04-24T10:00:00+00:00",
                "valid_from": "2026-04-24T10:00:00+00:00",
                "valid_to": "2999-01-01T00:00:00+00:00",
            },
        },
    )
    store.upsert_graph_state(
        subject_name="ReleaseTrainGamma",
        attribute="status",
        value_text="green",
        source="graph-parity-fixture",
        metadata=metadata,
    )
    store.upsert_graph_state(
        subject_name="ReleaseTrainGamma",
        attribute="status",
        value_text="blocked",
        source="graph-parity-fixture",
        metadata=metadata,
    )
    store.upsert_graph_state(
        subject_name="AuroraDelta",
        attribute="deployment",
        value_text="green",
        source="graph-parity-fixture",
        metadata=metadata,
    )
    store.get_or_create_entity("ProjectAuroraDelta")
    store.merge_entity_alias(alias_name="ProjectAuroraDelta", target_name="AuroraDelta")
    return {
        "principal_scope_key": PRINCIPAL_SCOPE,
        "queries": {
            "expired": "ExpiredWindowAlpha availability",
            "current": "CurrentWindowBeta availability",
            "conflict": "ReleaseTrainGamma blocked status",
            "alias": "ProjectAuroraDelta deployment",
        },
    }


def graph_trace_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_type": row.get("row_type", ""),
        "fact_class": row.get("fact_class", ""),
        "match_mode": row.get("match_mode", ""),
        "retrieval_source": row.get("retrieval_source", ""),
        "graph_backend_status": row.get("graph_backend_status", ""),
        "matched_alias": row.get("matched_alias", ""),
        "valid_to": row.get("valid_to", ""),
        "conflict_value": row.get("conflict_value", ""),
        "graph_fallback_reason": row.get("graph_fallback_reason", ""),
    }
