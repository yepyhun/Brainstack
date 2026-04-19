# ruff: noqa: E402

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from tests._host_import_shims import install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack.control_plane import build_working_memory_packet
from brainstack.db import BrainstackStore


def test_task_policy_can_follow_owner_parser_signal_without_query_cues(monkeypatch, tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    try:
        monkeypatch.setattr(
            "brainstack.control_plane.parse_task_lookup_query",
            lambda query, timezone_name="UTC": {
                "item_type": "task",
                "due_date": "",
                "date_scope": "undated",
                "followup_only": False,
            },
        )

        packet = build_working_memory_packet(
            store,
            query="Carry this forward.",
            session_id="phase38-1-task-signal",
            principal_scope_key="",
            profile_match_limit=4,
            continuity_recent_limit=4,
            continuity_match_limit=4,
            transcript_match_limit=2,
            transcript_char_budget=560,
            graph_limit=6,
            corpus_limit=4,
            corpus_char_budget=700,
        )

        assert packet["policy"]["mode"] == "compact"
        assert packet["policy"]["graph_limit"] == 0
        assert packet["policy"]["corpus_limit"] == 0
    finally:
        store.close()


def test_temporal_route_shapes_policy_from_retrieval_route_without_control_plane_temporal_cues(monkeypatch, tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    try:
        monkeypatch.setattr(
            "brainstack.control_plane.retrieve_executive_context",
            lambda *args, **kwargs: {
                "profile_items": [],
                "matched": [],
                "recent": [],
                "transcript_rows": [],
                "graph_rows": [],
                "corpus_rows": [],
                "task_rows": [],
                "operating_rows": [],
                "channels": [],
                "fused_candidates": [],
                "lookup_semantics": None,
                "routing": {
                    "requested_mode": "temporal",
                    "applied_mode": "temporal",
                    "source": "test",
                    "reason": "synthetic temporal route",
                    "fallback_used": False,
                    "bounds": {},
                },
            },
        )

        packet = build_working_memory_packet(
            store,
            query="Atlas ordering proof",
            session_id="phase38-1-temporal-route",
            principal_scope_key="",
            profile_match_limit=4,
            continuity_recent_limit=4,
            continuity_match_limit=4,
            transcript_match_limit=2,
            transcript_char_budget=560,
            graph_limit=6,
            corpus_limit=4,
            corpus_char_budget=700,
        )

        assert packet["routing"]["requested_mode"] == "temporal"
        assert packet["routing"]["applied_mode"] == "temporal"
        assert packet["policy"]["show_graph_history"] is True
        assert packet["policy"]["graph_limit"] >= 4
        assert packet["policy"]["transcript_char_budget"] >= 720
    finally:
        store.close()
