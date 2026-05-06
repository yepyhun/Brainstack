from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider


def _provider(tmp_path: Path, extractor, *, transcript: str) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "tier2_transcript_limit": 4,
            "tier2_timeout_seconds": 2,
            "_tier2_extractor": extractor,
        }
    )
    provider.initialize(
        "typed-graph-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    provider._store.add_transcript_entry(
        session_id="typed-graph-session",
        turn_number=1,
        kind="turn",
        content=transcript,
        source="test",
        metadata=provider._scoped_metadata(),
    )
    return provider


def _active_graph_relations(provider: BrainstackMemoryProvider) -> list[dict[str, str]]:
    assert provider._store is not None
    rows = provider._store.conn.execute(
        """
        SELECT s.canonical_name AS subject, r.predicate, r.object_text, r.metadata_json
        FROM graph_relations r
        JOIN graph_entities s ON s.id = r.subject_entity_id
        WHERE r.active = 1
        ORDER BY r.id
        """
    ).fetchall()
    return [
        {
            "subject": str(row["subject"]),
            "predicate": str(row["predicate"]),
            "object": str(row["object_text"]),
            "metadata_json": str(row["metadata_json"]),
        }
        for row in rows
    ]


def test_source_backed_typed_relation_populates_graph_and_doctor_state(tmp_path: Path) -> None:
    def extractor(*args, **kwargs):
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
            "_meta": {"json_parse_status": "ok", "parse_context": "test"},
        }

    provider = _provider(
        tmp_path,
        extractor,
        transcript="User: System Alpha is inspired by Capability Atlas.",
    )
    try:
        result = provider._run_tier2_batch(
            session_id="typed-graph-session",
            turn_number=1,
            trigger_reason="typed_graph_fixture",
        )

        assert result["status"] == "ok"
        assert result["writes_performed"] == 1
        assert result["action_counts"]["ADD"] == 1
        relations = _active_graph_relations(provider)
        assert [(row["subject"], row["predicate"], row["object"]) for row in relations] == [
            ("System Alpha", "inspired_by", "Capability Atlas")
        ]
        metadata = json.loads(relations[0]["metadata_json"])
        lineage = metadata["graph_source_lineage"]
        assert lineage["schema"] == "brainstack.graph_source_lineage.v1"
        assert lineage["status"] == "active"
        assert lineage["source_kind"] == "turn"
        assert lineage["graph_kind"] == "relation"
        assert metadata["tier2_decision_core"]["truth_eligible"] is True

        doctor = provider.memory_kernel_doctor(strict=True)
        graph_producer = doctor["capabilities"]["graph_producer"]
        assert graph_producer["status"] == "active"
        assert graph_producer["producer_state"] == "projected"
        assert graph_producer["reason_code"] == "GRAPH_PRODUCER_PROJECTED_TYPED_INPUT"
        assert graph_producer["graph_row_counts"]["relations"] == 1
    finally:
        provider.shutdown()


def test_assistant_authored_typed_relation_stays_rejected_and_inspectable(tmp_path: Path) -> None:
    def extractor(*args, **kwargs):
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
            "_meta": {"json_parse_status": "ok", "parse_context": "test"},
        }

    provider = _provider(
        tmp_path,
        extractor,
        transcript="Assistant: System Alpha is inspired by Capability Atlas.",
    )
    try:
        result = provider._run_tier2_batch(
            session_id="typed-graph-session",
            turn_number=1,
            trigger_reason="typed_graph_fixture",
        )

        assert result["status"] == "ok"
        assert result["writes_performed"] == 0
        assert result["action_counts"]["REJECT_ASSISTANT_AUTHORED"] == 1
        assert _active_graph_relations(provider) == []
        doctor = provider.memory_kernel_doctor(strict=True)
        graph_producer = doctor["capabilities"]["graph_producer"]
        assert graph_producer["status"] == "active"
        assert graph_producer["producer_state"] == "rejected"
        assert graph_producer["reason_code"] == "GRAPH_PRODUCER_TYPED_INPUT_REJECTED"
        assert graph_producer["latest_graph_candidate_counts"]["relations"] == 1
    finally:
        provider.shutdown()


def test_empty_graph_is_reported_as_no_input_not_backend_failure(tmp_path: Path) -> None:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "typed-graph-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    try:
        doctor = provider.memory_kernel_doctor(strict=True)
        graph = doctor["capabilities"]["graph"]
        graph_producer = doctor["capabilities"]["graph_producer"]

        assert graph["status"] == "active"
        assert graph_producer["requested"] is False
        assert graph_producer["status"] == "active"
        assert graph_producer["producer_state"] == "no_input"
        assert graph_producer["reason_code"] == "GRAPH_PRODUCER_NO_INPUT"
    finally:
        provider.shutdown()
