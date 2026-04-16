"""Focused tests for Brainstack continuity lifecycle state."""

# ruff: noqa: E402

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from tests._host_import_shims import install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider


def _make_provider(tmp_path, session_id: str, **config):
    base = Path(tmp_path)
    provider = BrainstackMemoryProvider(
        config={
            "db_path": str(base / "brainstack.db"),
            **config,
        }
    )
    provider.initialize(session_id, hermes_home=str(base))
    return provider


class TestBrainstackLifecycleState:
    def test_pre_compress_records_snapshot_frontier(self, tmp_path):
        provider = _make_provider(tmp_path, "session-lifecycle-pre")
        try:
            provider.sync_turn(
                "Keep the compaction audit trail bounded and easy to inspect.",
                "Understood. I will keep the audit trail bounded.",
                session_id="session-lifecycle-pre",
            )
            provider.on_pre_compress(
                [
                    {"role": "user", "content": "Keep the compaction audit trail bounded and easy to inspect."},
                    {"role": "assistant", "content": "Understood. I will keep the audit trail bounded."},
                ]
            )
            rows = provider._store.recent_continuity(session_id="session-lifecycle-pre", limit=10)
            snapshot_row = next(row for row in rows if row["kind"] == "compression_snapshot")
            provenance = (snapshot_row.get("metadata") or {}).get("provenance") or {}
            assert provenance["input_message_count"] == 2
            assert provenance["captured_message_count"] == 2
            assert provenance["window_digest"]
            assert len(provenance["source_window"]) == 2
            state = provider._store.get_continuity_lifecycle_state(session_id="session-lifecycle-pre")
            assert state is not None
            assert state["last_snapshot_kind"] == "compression_snapshot"
            assert state["current_frontier_turn_number"] == 1
            assert state["last_snapshot_turn_number"] == 1
            assert state["last_snapshot_message_count"] == 2
            assert state["last_snapshot_input_count"] == 2
            assert state["last_snapshot_digest"]
            assert state["last_snapshot_at"]
            assert state["last_finalized_turn_number"] == 0
            assert state["last_finalized_at"] == ""
        finally:
            provider.shutdown()

    def test_session_end_finalizes_lifecycle_state(self, tmp_path):
        provider = _make_provider(tmp_path, "session-lifecycle-final")
        try:
            provider.sync_turn(
                "The release checklist still belongs to the Friday ship thread.",
                "Noted. I will keep the Friday ship thread active.",
                session_id="session-lifecycle-final",
            )
            provider.on_session_end(
                [
                    {"role": "user", "content": "The release checklist still belongs to the Friday ship thread."},
                    {"role": "assistant", "content": "Noted. I will keep the Friday ship thread active."},
                ]
            )
            state = provider._store.get_continuity_lifecycle_state(session_id="session-lifecycle-final")
            assert state is not None
            assert state["last_snapshot_kind"] == "session_summary"
            assert state["current_frontier_turn_number"] == 1
            assert state["last_snapshot_turn_number"] == 1
            assert state["last_finalized_turn_number"] == 1
            assert state["last_finalized_at"]
        finally:
            provider.shutdown()
