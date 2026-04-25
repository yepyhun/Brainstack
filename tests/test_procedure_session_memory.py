from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "procedure-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def test_procedure_memory_is_recallable_operating_evidence_not_execution_tool(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "operating",
                    "stable_key": "procedure:phase-workflow",
                    "record_type": "procedure_memory",
                    "content": "Procedure memory: reread the current phase plan before executing a new phase.",
                    "source_role": "operator",
                    "authority_class": "operating",
                    "metadata": {"semantic_terms": ["phase boundary procedure"]},
                },
                trusted_write_origin="test_operator",
            )
        )
        assert receipt["status"] == "committed"

        recall = json.loads(
            provider.handle_tool_call("brainstack_recall", {"query": "phase boundary procedure"})
        )
        assert recall["selected_evidence"]["operating"]
        assert "procedure memory" in recall["final_packet"]["preview"]

        tool_names = {schema["name"] for schema in provider.get_tool_schemas()}
        assert "brainstack_execute" not in tool_names
        assert "brainstack_schedule" not in tool_names
        assert "brainstack_approve" not in tool_names
    finally:
        provider.shutdown()


def test_session_state_respects_temporal_expiry_in_keyword_and_semantic_recall(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        expired = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "operating",
                    "stable_key": "session:expired",
                    "record_type": "session_state",
                    "content": "Session state: obsolete temporary handoff is pending.",
                    "source_role": "operator",
                    "authority_class": "operating",
                    "metadata": {
                        "temporal": {"valid_to": "2000-01-01T00:00:00+00:00"},
                        "semantic_terms": ["obsolete temporary handoff"],
                    },
                },
                trusted_write_origin="test_operator",
            )
        )
        active = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "operating",
                    "stable_key": "session:active",
                    "record_type": "session_state",
                    "content": "Session state: current phase handoff is active.",
                    "source_role": "operator",
                    "authority_class": "operating",
                    "metadata": {
                        "temporal": {"valid_to": "2999-01-01T00:00:00+00:00"},
                        "semantic_terms": ["current phase handoff"],
                    },
                },
                trusted_write_origin="test_operator",
            )
        )
        assert expired["status"] == "committed"
        assert active["status"] == "committed"

        expired_recall = json.loads(
            provider.handle_tool_call("brainstack_recall", {"query": "obsolete temporary handoff"})
        )
        assert expired_recall["selected_evidence"].get("operating", []) == []

        active_recall = json.loads(
            provider.handle_tool_call("brainstack_recall", {"query": "current phase handoff"})
        )
        assert active_recall["selected_evidence"]["operating"]
        assert "current phase handoff" in active_recall["final_packet"]["preview"]
    finally:
        provider.shutdown()
