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
        "read-diagnostics-seam",
        platform="test",
        user_id="user",
        chat_id="chat",
        thread_id="thread",
    )
    return provider


def test_read_diagnostics_seam_keeps_recall_inspect_stats_stable(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        provider._store.upsert_profile_item(
            stable_key="preference:diagnostics",
            category="preference",
            content="Diagnostics should remain read-only and inspectable.",
            source="test",
            confidence=0.99,
            metadata=provider._scoped_metadata(),
        )

        recall = json.loads(provider.handle_tool_call("brainstack_recall", {"query": "diagnostics inspectable"}))
        inspect = json.loads(provider.handle_tool_call("brainstack_inspect", {"query": "diagnostics inspectable"}))
        stats = json.loads(provider.handle_tool_call("brainstack_stats", {"strict": True}))

        assert recall["schema"] == "brainstack.tool_recall.v1"
        assert recall["read_only"] is True
        assert "evidence_count" not in recall
        assert recall["diagnostic_evidence_count"] >= 1
        assert recall["answerable_evidence_count"] >= 1
        assert recall["memory_answerability"]["can_answer"] is True
        assert inspect["schema"] == "brainstack.tool_inspect.v1"
        assert inspect["read_only"] is True
        assert inspect["report"]["schema"] == "brainstack.query_inspect.v1"
        assert stats["schema"] == "brainstack.tool_stats.v1"
        assert stats["read_only"] is True
        assert stats["report"]["schema"] == "brainstack.memory_kernel_doctor.v1"
        assert stats["lifecycle"]["schema"] == "brainstack.provider_lifecycle.v1"
    finally:
        provider.shutdown()


def test_read_diagnostics_seam_reports_uninitialized_store_without_mutation(tmp_path: Path) -> None:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )

    inspect = json.loads(provider.handle_tool_call("brainstack_inspect", {"query": "anything"}))
    stats = json.loads(provider.handle_tool_call("brainstack_stats", {"strict": True}))

    assert inspect["schema"] == "brainstack.tool_inspect.v1"
    assert inspect["report"]["error"] == "Brainstack store is not initialized."
    assert stats["report"]["verdict"] == "fail"
    assert stats["lifecycle"]["status"] == "unavailable"
