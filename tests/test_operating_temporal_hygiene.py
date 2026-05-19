from __future__ import annotations

from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.operating_temporal_report import build_operating_temporal_hygiene_report
from brainstack.operating_temporal import suggest_operating_expiry_from_text
from brainstack.operating_truth import (
    OPERATING_RECORD_CURRENT_COMMITMENT,
    OPERATING_RECORD_PROCEDURE_MEMORY,
)
from brainstack.retrieval import _render_operating_truth_section


PRINCIPAL_SCOPE = "principal:operating-temporal-hygiene"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def test_structured_expires_after_seconds_derives_valid_window_without_english_text(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        row_id = store.upsert_operating_record(
            stable_key="commitment:multilingual-structured-expiry",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_CURRENT_COMMITMENT,
            content="我会继续处理这个任务。",
            owner="agent",
            source="test",
            metadata={
                "temporal": {"expires_after_seconds": 600},
                "semantic_terms": ["multilingual structured expiry"],
            },
        )

        row = store.conn.execute(
            "SELECT metadata_json FROM operating_records WHERE id = ?",
            (row_id,),
        ).fetchone()
        assert row is not None
        metadata = store.list_operating_records(
            principal_scope_key=PRINCIPAL_SCOPE,
            record_types=[OPERATING_RECORD_CURRENT_COMMITMENT],
            limit=1,
        )[0]["metadata"]
        assert metadata["temporal"]["expires_after_seconds"] == 600
        assert metadata["temporal"]["valid_from"]
        assert metadata["temporal"]["valid_to"]
        assert metadata["operating_temporal"]["authority"] == "structured_temporal_metadata"
    finally:
        store.close()


def test_expired_structured_commitment_is_suppressed_from_list_and_search(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_operating_record(
            stable_key="commitment:expired",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_CURRENT_COMMITMENT,
            content="Expired commitment: obsolete handoff within ten minutes.",
            owner="agent",
            source="test",
            metadata={
                "temporal": {"valid_to": "2000-01-01T00:00:00+00:00"},
                "semantic_terms": ["obsolete handoff"],
            },
        )

        assert (
            store.list_operating_records(
                principal_scope_key=PRINCIPAL_SCOPE,
                record_types=[OPERATING_RECORD_CURRENT_COMMITMENT],
            )
            == []
        )
        assert (
            store.search_operating_records(
                query="obsolete handoff",
                principal_scope_key=PRINCIPAL_SCOPE,
                record_types=[OPERATING_RECORD_CURRENT_COMMITMENT],
            )
            == []
        )
    finally:
        store.close()


def test_raw_text_duration_is_not_core_authority_and_renders_unknown_expiry(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        row_id = store.upsert_operating_record(
            stable_key="commitment:raw-text-only",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_CURRENT_COMMITMENT,
            content="I will reply within 10 minutes.",
            owner="agent",
            source="test",
            metadata={"semantic_terms": ["raw text duration"]},
        )
        store.conn.execute(
            "UPDATE operating_records SET created_at = ?, updated_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", "2000-01-01T00:00:00+00:00", row_id),
        )
        store.conn.commit()

        rows = store.search_operating_records(
            query="reply minutes",
            principal_scope_key=PRINCIPAL_SCOPE,
            limit=1,
        )
        assert rows
        metadata = rows[0]["metadata"]
        assert metadata.get("temporal", {}).get("valid_to") is None
        assert metadata["operating_temporal"]["authority"] == "unknown_expiry"

        rendered = _render_operating_truth_section(rows, provenance_mode="compact")
        assert "unknown expiry" in rendered
        assert "volatile record" in rendered

        suggestion = suggest_operating_expiry_from_text(
            "I will reply within 10 minutes.",
            created_at="2000-01-01T00:00:00+00:00",
        )
        assert suggestion is not None
        assert suggestion["authority"] == "suggestion_only"
    finally:
        store.close()


def test_procedure_memory_with_time_words_does_not_get_expiry_warning(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_operating_record(
            stable_key="procedure:time-word",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_PROCEDURE_MEMORY,
            content="Procedure: wait 10 minutes only when a rate limit explicitly says so.",
            owner="operator",
            source="test",
            metadata={"semantic_terms": ["rate limit procedure"]},
        )

        rows = store.search_operating_records(
            query="rate limit procedure",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_types=[OPERATING_RECORD_PROCEDURE_MEMORY],
            limit=1,
        )
        assert rows
        rendered = _render_operating_truth_section(rows, provenance_mode="compact")
        assert "rate limit" in rendered
        assert "unknown expiry" not in rendered
        assert "expired" not in rendered
    finally:
        store.close()


def test_temporal_hygiene_report_is_public_safe_dry_run(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_operating_record(
            stable_key="commitment:secret-raw-text",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_CURRENT_COMMITMENT,
            content="SECRET_PUBLIC_SAFE_FIXTURE will reply within 10 minutes.",
            owner="agent",
            source="test",
            metadata={},
        )

        report = build_operating_temporal_hygiene_report(store.conn)
        assert report["schema"] == "brainstack.operating_temporal_hygiene_report.v1"
        assert report["read_only"] is True
        assert report["raw_content_included"] is False
        assert report["unknown_expiry_candidate_count"] >= 1
        serialized = str(report)
        assert "SECRET_PUBLIC_SAFE_FIXTURE" not in serialized
        assert report["dry_run_candidates"][0]["mutation"] == "none"
    finally:
        store.close()
