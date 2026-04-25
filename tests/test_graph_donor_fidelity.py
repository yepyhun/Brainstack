from __future__ import annotations

import json
from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.graph import ingest_graph_evidence_with_receipt
from brainstack.graph_evidence import GraphEvidenceItem
from brainstack.tier2_extractor import _normalize_states


PRINCIPAL_SCOPE = "principal:graph-donor-fidelity"


def _open_store(tmp_path: Path, *, graph_backend: str = "sqlite") -> BrainstackStore:
    store = BrainstackStore(
        str(tmp_path / "brainstack.sqlite3"),
        graph_backend=graph_backend,
        corpus_backend="sqlite",
    )
    store.open()
    return store


def _selected_graph(report: dict) -> list[dict]:
    return list(report["selected_evidence"]["graph"])


def test_graph_temporal_scope_reaches_validity_column_and_query_projection(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Kimi K2.6 Access Window",
            attribute="availability",
            value_text="remaining for 15 hours",
            source="temporal-fixture",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "temporal": {
                    "observed_at": "2026-04-23T15:00:00+00:00",
                    "valid_from": "2026-04-23T15:00:00+00:00",
                    "valid_to": "2026-04-24T06:00:00+00:00",
                },
            },
        )

        row = store.conn.execute(
            """
            SELECT valid_to
            FROM graph_states
            WHERE attribute = 'availability'
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row["valid_to"] == "2026-04-24T06:00:00+00:00"

        report = build_query_inspect(
            store,
            query="Kimi K2.6 Access Window availability",
            session_id="session:temporal",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )

        graph_rows = _selected_graph(report)
        assert graph_rows
        assert graph_rows[0]["fact_class"] == "explicit_state_expired"
        assert graph_rows[0]["valid_to"] == "2026-04-24T06:00:00+00:00"
        assert "Brainstack Graph Truth" in report["final_packet"]["sections"]
    finally:
        store.close()


def test_relative_duration_graph_state_derives_validity_window(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Kimi K2.6 Access Window",
            attribute="availability",
            value_text="15 hours remaining",
            source="relative-duration-fixture",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "temporal": {
                    "observed_at": "2026-04-23T10:00:00+00:00",
                    "valid_from": "2026-04-23T10:00:00+00:00",
                },
            },
        )

        row = store.conn.execute(
            """
            SELECT valid_to, metadata_json
            FROM graph_states
            WHERE attribute = 'availability'
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row["valid_to"] == "2026-04-24T01:00:00+00:00"
        assert "relative_duration_validity" in row["metadata_json"]

        report = build_query_inspect(
            store,
            query="Kimi K2.6 availability",
            session_id="session:relative-duration",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )
        graph_rows = _selected_graph(report)
        assert graph_rows
        assert graph_rows[0]["fact_class"] == "explicit_state_expired"
        assert (
            "[state:expired] Kimi K2.6 Access Window availability=15 hours remaining"
            in report["final_packet"]["preview"]
        )
    finally:
        store.close()


def test_relative_duration_graph_state_without_column_expiry_is_not_current(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Legacy Kimi Access",
            attribute="availability",
            value_text="15 hours remaining",
            source="legacy-fixture",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "graph_source_lineage": {
                    "observed_at": "2026-04-23T10:00:00+00:00",
                    "source_kind": "tier2",
                },
            },
        )
        legacy_metadata = {
            "graph_kind": "state",
            "source_kind": "explicit",
            "graph_source_lineage": {
                "observed_at": "2026-04-23T10:00:00+00:00",
                "source_kind": "tier2",
            },
        }
        store.conn.execute(
            "UPDATE graph_states SET valid_to = NULL, metadata_json = ? WHERE attribute = 'availability'",
            (json.dumps(legacy_metadata, ensure_ascii=True, sort_keys=True),),
        )
        store.conn.commit()

        report = build_query_inspect(
            store,
            query="Legacy Kimi Access availability",
            session_id="session:legacy-relative-duration",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )
        graph_rows = _selected_graph(report)
        assert graph_rows
        assert graph_rows[0]["fact_class"] == "explicit_state_expired"
        assert "[state:current] Legacy Kimi Access availability=15 hours remaining" not in report["final_packet"][
            "preview"
        ]
    finally:
        store.close()


def test_scoped_relative_duration_graph_state_without_column_expiry_is_not_current(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Scoped Kimi Access",
            attribute="availability",
            value_text="15 hours remaining for autonomous research tasks",
            source="legacy-scoped-fixture",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "temporal": {
                    "observed_at": "2026-04-23T10:00:00+00:00",
                    "valid_from": "2026-04-23T10:00:00+00:00",
                },
            },
        )
        store.conn.execute("UPDATE graph_states SET valid_to = NULL WHERE attribute = 'availability'")
        store.conn.commit()

        report = build_query_inspect(
            store,
            query="15 hours remaining autonomous research",
            session_id="session:scoped-relative-duration",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )
        graph_rows = _selected_graph(report)
        assert graph_rows
        assert graph_rows[0]["fact_class"] == "explicit_state_expired"
        assert "[state:current] Scoped Kimi Access availability=15 hours remaining" not in report["final_packet"][
            "preview"
        ]
    finally:
        store.close()


def test_remaining_time_attribute_duration_values_expire_without_column_validity(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        for attribute, value_text in (("remaining_time", "15 hours"), ("remaining_hours", "15")):
            store.upsert_graph_state(
                subject_name=f"Legacy {attribute}",
                attribute=attribute,
                value_text=value_text,
                source=f"legacy-{attribute}",
                metadata={
                    "principal_scope_key": PRINCIPAL_SCOPE,
                    "temporal": {
                        "observed_at": "2026-04-23T10:00:00+00:00",
                        "valid_from": "2026-04-23T10:00:00+00:00",
                    },
                },
            )
        store.conn.execute("UPDATE graph_states SET valid_to = NULL")
        store.conn.commit()

        report = build_query_inspect(
            store,
            query="remaining time 15 hours",
            session_id="session:remaining-time-field",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=8,
        )
        graph_rows = _selected_graph(report)
        assert graph_rows
        stale_rows = [
            row
            for row in graph_rows
            if row["predicate"] in {"remaining_time", "remaining_hours"}
        ]
        assert stale_rows
        assert all(row["fact_class"] == "explicit_state_expired" for row in stale_rows)
    finally:
        store.close()


def test_tier2_relative_duration_without_absolute_validity_is_not_current(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Tier2 Kimi Usage",
            attribute="remaining_hours",
            value_text="15",
            source="tier2:idle_window",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "batch_reason": "idle_window",
            },
        )

        report = build_query_inspect(
            store,
            query="Tier2 Kimi Usage remaining hours",
            session_id="session:tier2-relative-duration",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )
        graph_rows = _selected_graph(report)
        assert graph_rows
        assert graph_rows[0]["fact_class"] == "explicit_state_expired"
        assert "[state:current] Tier2 Kimi Usage remaining_hours=15" not in report["final_packet"]["preview"]
    finally:
        store.close()


def test_tier2_unbounded_volatile_status_is_not_current_authority(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Tomi",
            attribute="testing_status",
            value_text="active testing of brainstack",
            source="tier2:idle_window",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "batch_reason": "idle_window",
            },
        )

        row = store.conn.execute(
            """
            SELECT valid_to
            FROM graph_states
            WHERE attribute = 'testing_status'
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row["valid_to"]

        report = build_query_inspect(
            store,
            query="Tomi testing status",
            session_id="session:tier2-volatile-status",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )
        graph_rows = _selected_graph(report)
        assert graph_rows
        assert graph_rows[0]["fact_class"] == "explicit_state_expired"
        assert "[state:current] Tomi testing_status=active testing of brainstack" not in report["final_packet"][
            "preview"
        ]
    finally:
        store.close()


def test_tier2_stable_graph_identity_is_not_over_suppressed(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Assistant model",
            attribute="model_engine",
            value_text="Kimi K2.6",
            source="tier2:idle_window",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "batch_reason": "idle_window",
            },
        )

        report = build_query_inspect(
            store,
            query="Assistant model engine Kimi",
            session_id="session:tier2-stable-identity",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )
        graph_rows = _selected_graph(report)
        assert graph_rows
        assert graph_rows[0]["fact_class"] == "explicit_state_current"
        assert "[state:current] Assistant model model_engine=Kimi K2.6" in report["final_packet"]["preview"]
    finally:
        store.close()


def test_tier2_assistant_self_role_is_not_current_authority(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Assistant",
            attribute="role",
            value_text="brainstack brain",
            source="tier2:idle_window",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "batch_reason": "idle_window",
            },
        )

        report = build_query_inspect(
            store,
            query="Assistant role brainstack brain",
            session_id="session:tier2-self-role",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )
        graph_rows = _selected_graph(report)
        assert graph_rows
        assert graph_rows[0]["fact_class"] == "explicit_state_expired"
        assert "[state:current] Assistant role=brainstack brain" not in report["final_packet"]["preview"]
    finally:
        store.close()


def test_tier2_volatile_state_with_explicit_future_validity_can_be_current(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Tomi",
            attribute="testing_status",
            value_text="active testing of brainstack",
            source="tier2:idle_window",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "batch_reason": "idle_window",
                "temporal": {
                    "observed_at": "2026-04-25T12:00:00+00:00",
                    "valid_from": "2026-04-25T12:00:00+00:00",
                    "valid_to": "2999-01-01T00:00:00+00:00",
                },
            },
        )

        report = build_query_inspect(
            store,
            query="Tomi testing status",
            session_id="session:tier2-explicit-window",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )
        graph_rows = _selected_graph(report)
        assert graph_rows
        assert graph_rows[0]["fact_class"] == "explicit_state_current"
    finally:
        store.close()


def test_fresh_relative_duration_graph_state_remains_current_inside_window(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Fresh Access Window",
            attribute="availability",
            value_text="15 hours remaining",
            source="fresh-relative-duration-fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        row = store.conn.execute(
            """
            SELECT valid_to
            FROM graph_states
            WHERE attribute = 'availability'
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row["valid_to"]

        report = build_query_inspect(
            store,
            query="Fresh Access Window availability",
            session_id="session:fresh-relative-duration",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )
        graph_rows = _selected_graph(report)
        assert graph_rows
        assert graph_rows[0]["fact_class"] == "explicit_state_current"
    finally:
        store.close()


def test_typed_graph_evidence_promotes_temporal_scope_to_state_validity(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        result = ingest_graph_evidence_with_receipt(
            store,
            source="typed-temporal-fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
            evidence_items=[
                GraphEvidenceItem(
                    kind="state",
                    subject="Timeboxed Tool Access",
                    attribute="availability",
                    value_text="active",
                    confidence=0.91,
                    temporal_scope={
                        "observed_at": "2026-04-23T10:00:00+00:00",
                        "valid_to": "2026-04-23T12:00:00+00:00",
                    },
                )
            ],
        )

        assert result["receipt"]["written_count"] == 1
        row = store.conn.execute(
            """
            SELECT valid_to, metadata_json
            FROM graph_states
            WHERE attribute = 'availability'
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row["valid_to"] == "2026-04-23T12:00:00+00:00"
        assert "temporal_scope" in row["metadata_json"]
        assert '"valid_to": "2026-04-23T12:00:00+00:00"' in row["metadata_json"]
    finally:
        store.close()


def test_tier2_state_normalization_preserves_only_grounded_iso_temporal_fields() -> None:
    states = _normalize_states(
        [
            {
                "subject": "Access Window",
                "attribute": "availability",
                "value": "active",
                "temporal": {
                    "observed_at": "2026-04-23T10:00:00+00:00",
                    "valid_to": "2026-04-23T12:00:00+00:00",
                },
            },
            {
                "subject": "Ungrounded Window",
                "attribute": "availability",
                "value": "active",
                "temporal": {"valid_to": "tomorrow"},
            },
        ]
    )

    assert states[0]["temporal"]["valid_to"] == "2026-04-23T12:00:00+00:00"
    assert "temporal" not in states[1]


def test_conflicting_current_state_projects_as_conflict_not_replacement(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Release Train",
            attribute="status",
            value_text="green",
            source="conflict-fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        conflict = store.upsert_graph_state(
            subject_name="Release Train",
            attribute="status",
            value_text="red",
            source="conflict-fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        assert conflict["status"] == "conflict"
        report = build_query_inspect(
            store,
            query="Release Train red status",
            session_id="session:conflict",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )

        graph_rows = _selected_graph(report)
        assert any(row["row_type"] == "conflict" for row in graph_rows)
        conflict_rows = [row for row in graph_rows if row["row_type"] == "conflict"]
        assert conflict_rows[0]["fact_class"] == "conflict"
        assert conflict_rows[0]["conflict_value"] == "red"
        assert "[conflict]" in report["final_packet"]["preview"]
    finally:
        store.close()


def test_entity_alias_merge_is_inspectable_and_searchable_without_collapsing_names(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Aurora",
            attribute="deployment",
            value_text="green",
            source="alias-fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        store.get_or_create_entity("Project Aurora")
        store.merge_entity_alias(alias_name="Project Aurora", target_name="Aurora")

        canonical = store.get_or_create_entity("Project Aurora")
        assert canonical["canonical_name"] == "Aurora"
        assert canonical["matched_alias"] == "Project Aurora"

        report = build_query_inspect(
            store,
            query="Project Aurora deployment",
            session_id="session:alias",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )

        graph_rows = _selected_graph(report)
        assert graph_rows
        assert graph_rows[0]["subject"] == "Aurora"
        assert graph_rows[0]["matched_alias"] == "Project Aurora"
        assert graph_rows[0]["match_mode"] == "alias_lexical"

        store.upsert_graph_state(
            subject_name="Aurorium",
            attribute="deployment",
            value_text="separate",
            source="alias-fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        alias_rows = store.conn.execute("SELECT alias_name FROM graph_entity_aliases").fetchall()
        assert [row["alias_name"] for row in alias_rows] == ["Project Aurora"]
    finally:
        store.close()


def test_graph_search_trace_reports_sqlite_and_degraded_external_modes(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Graph Trace Probe",
            attribute="mode",
            value_text="inspectable",
            source="trace-fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        report = build_query_inspect(
            store,
            query="Graph Trace Probe inspectable",
            session_id="session:trace",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )
        graph_rows = _selected_graph(report)
        assert graph_rows[0]["retrieval_source"] == "graph.sqlite_lexical"
        assert graph_rows[0]["match_mode"] == "sqlite_lexical"
        assert graph_rows[0]["graph_backend_status"] == "active"

        store._graph_backend_name = "kuzu"
        store._graph_backend = None
        store._graph_backend_error = "kuzu unavailable in fixture"
        degraded = build_query_inspect(
            store,
            query="Graph Trace Probe inspectable",
            session_id="session:trace",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )
        degraded_graph_rows = _selected_graph(degraded)
        assert degraded_graph_rows[0]["graph_backend_requested"] == "kuzu"
        assert degraded_graph_rows[0]["graph_backend_status"] == "degraded"
        assert degraded_graph_rows[0]["graph_fallback_reason"] == "kuzu unavailable in fixture"
    finally:
        store.close()
