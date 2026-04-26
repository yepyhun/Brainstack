from __future__ import annotations

import json
from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.literal_index import classify_literal, detect_literal_tokens, literal_slot_match

PRINCIPAL_SCOPE = "principal:literal-event"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _inspect(store: BrainstackStore, query: str, *, session_id: str = "literal-session") -> dict:
    return build_query_inspect(
        store,
        query=query,
        session_id=session_id,
        principal_scope_key=PRINCIPAL_SCOPE,
        profile_match_limit=4,
        continuity_match_limit=4,
        continuity_recent_limit=0,
        transcript_match_limit=4,
        operating_match_limit=0,
        graph_limit=0,
        corpus_limit=0,
    )


def test_exact_literal_sidecar_supports_direct_literal_recall(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_profile_item(
            stable_key="debug_marker:1231231X",
            category="preference",
            content="Debug marker slot value is 1231231X.",
            source="literal.fixture",
            confidence=0.99,
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        report = _inspect(store, "debug marker 1231231X")
        row = report["selected_evidence"]["profile"][0]

        assert row["stable_key"] == "debug_marker:1231231X"
        assert any(token["value"] == "1231231X" for token in row["literal_tokens"])
        assert report["memory_answerability"]["can_answer"] is True
        assert report["memory_answerability"]["answer_evidence_ids"] == ["profile:debug_marker:1231231X"]
    finally:
        store.close()


def test_literal_slot_recall_does_not_require_query_to_contain_full_literal(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_profile_item(
            stable_key="debug_marker:1231231Y",
            category="preference",
            content="Debug marker slot value is 1231231Y.",
            source="literal.fixture",
            confidence=0.4,
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        store.upsert_profile_item(
            stable_key="debug_marker:1231231X",
            category="preference",
            content="Debug marker slot value is 1231231X.",
            source="literal.fixture",
            confidence=0.99,
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        report = _inspect(store, "X-re vegzodo debug kodom")
        profile_rows = report["selected_evidence"]["profile"]

        assert profile_rows[0]["stable_key"] == "debug_marker:1231231X"
        assert profile_rows[0]["literal_slot_match"]["matched"] is True
        assert "1231231X" in report["final_packet"]["preview"]
        assert "1231231Y" not in profile_rows[0]["excerpt"]
    finally:
        store.close()


def test_literal_detection_redacts_private_paths_and_secret_shaped_values(tmp_path: Path) -> None:
    assert classify_literal("/home/lauratom/private/key.txt") == "private_path"
    assert classify_literal("sk-abcdefghijklmnopqrstuvwxyz123456") == "secret_shaped"

    store = _open_store(tmp_path)
    try:
        store.upsert_profile_item(
            stable_key="debug:path",
            category="preference",
            content="Debug file path is /home/lauratom/private/key.txt and token sk-abcdefghijklmnopqrstuvwxyz123456.",
            source="literal.fixture",
            confidence=0.99,
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        report = _inspect(store, "debug file path token")
        preview = report["final_packet"]["preview"]
        row = report["selected_evidence"]["profile"][0]

        assert "/home/lauratom/private/key.txt" not in preview
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in preview
        assert "/home/lauratom/private/key.txt" not in row["excerpt"]
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in row["excerpt"]
        assert any(token["class"] == "private_path" for token in row["literal_tokens"])
        assert any(token["class"] == "secret_shaped" for token in row["literal_tokens"])
    finally:
        store.close()


def test_user_turn_event_sidecar_and_backfill_are_bounded_and_idempotent(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        row_id = store.conn.execute(
            """
            INSERT INTO transcript_entries (session_id, turn_number, kind, content, source, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "old-session",
                7,
                "user_request",
                "Please remember the migration marker OldMarker777X.",
                "legacy.fixture",
                json.dumps({"principal_scope_key": PRINCIPAL_SCOPE}),
                "2026-04-25T00:00:00+00:00",
            ),
        ).lastrowid
        assert row_id is not None
        store.conn.execute(
            "INSERT INTO transcript_fts(rowid, content, session_id, kind) VALUES (?, ?, ?, ?)",
            (int(row_id), "Please remember the migration marker OldMarker777X.", "old-session", "user_request"),
        )
        store.conn.commit()

        dry_run = store.backfill_literal_event_sidecars(dry_run=True)
        first = store.backfill_literal_event_sidecars(dry_run=False)
        second = store.backfill_literal_event_sidecars(dry_run=False)

        assert dry_run["updated"] >= 1
        assert first["updated"] >= 1
        assert second["updated"] == 0

        metadata_json = store.conn.execute(
            "SELECT metadata_json FROM transcript_entries WHERE id = ?",
            (int(row_id),),
        ).fetchone()["metadata_json"]
        metadata = json.loads(metadata_json)
        event = metadata["conversation_event"]
        assert event["schema"] == "brainstack.user_turn_event_index.v1"
        assert event["transcript_row_id"] == int(row_id)
        assert event["event_type"] == "user_request"
        assert event["bounded_scope_only"] is True
        assert "raw_text" not in event
        assert any(token["value"] == "OldMarker777X" for token in event["literal_tokens"])
    finally:
        store.close()


def test_assistant_event_residue_is_supporting_context_not_user_fact(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.add_transcript_entry(
            session_id="literal-session",
            turn_number=3,
            kind="assistant",
            content="Assistant guessed that the marker could be 1231231Y.",
            source="assistant.fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        report = _inspect(store, "assistant marker 1231231Y")
        assert report["selected_evidence"]["transcript"]
        answerability = report["memory_answerability"]
        assert answerability["can_answer"] is False
        assert answerability["answer_evidence_ids"] == []
        assert answerability["supporting_context_ids"] == ["transcript:1"]
    finally:
        store.close()


def test_literal_slot_match_uses_anchor_plus_shape_not_shape_alone() -> None:
    metadata = {
        "literal_index": {
            "literal_tokens": detect_literal_tokens("Debug marker slot value is 1231231X."),
            "semantic_anchor_text": "Debug marker slot value is.",
        }
    }
    assert literal_slot_match(query="X suffix unknown thing", text="", metadata=metadata)["matched"] is False
    matched = literal_slot_match(query="X suffix debug thing", text="", metadata=metadata)
    assert matched["matched"] is True
