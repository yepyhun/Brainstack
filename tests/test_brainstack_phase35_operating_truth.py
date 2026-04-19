# ruff: noqa: E402
"""Targeted regression tests for phase 35 operating truth."""

import importlib.util
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location(
    "phase35_host_import_shims",
    _host_shims_path,
)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider
from brainstack.control_plane import build_working_memory_packet


def _make_provider(tmp_path, session_id: str, **init_kwargs):
    provider = BrainstackMemoryProvider(config={"db_path": str(Path(tmp_path) / "brainstack.db")})
    provider.initialize(session_id, hermes_home=str(tmp_path), **init_kwargs)
    return provider


def _operating_truth_text() -> str:
    return (
        "Active work:\n"
        "- Phase 35 operating truth rollout\n\n"
        "Open decisions:\n"
        "- Whether owner-first retrieval should consult operating truth before continuity fallback\n\n"
        "Current commitment:\n"
        "- Finish the phase without adding heuristic sprawl\n\n"
        "Next step:\n"
        "- Wire operating records into retrieval and operating context\n\n"
        "External owner:\n"
        "- Nous authentication belongs to the provider runtime, not Brainstack"
    )


def test_operating_truth_commits_into_first_class_storage_and_renders_in_operating_context(tmp_path):
    provider = _make_provider(
        tmp_path,
        "operating-truth-commit",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="workspace-a",
    )
    try:
        block = provider.prefetch(_operating_truth_text(), session_id="operating-truth-commit")
        store = provider._store
        assert store is not None

        rows = store.list_operating_records(principal_scope_key=provider._principal_scope_key, limit=12)
        record_types = {str(row.get("record_type") or "") for row in rows}
        prompt_block = provider.system_prompt_block()
        trace = provider.memory_operation_trace()

        assert {
            "active_work",
            "open_decision",
            "current_commitment",
            "next_step",
            "external_owner_pointer",
        }.issubset(record_types)
        assert "## Brainstack Memory Operation Receipt" in block
        assert "# Brainstack Operating Context" in prompt_block
        assert "Phase 35 operating truth rollout" in prompt_block
        assert "Current commitments:" in prompt_block
        assert "External owner pointers:" in prompt_block
        assert trace is not None
        assert trace["last_write_receipt"]["owner"] == "brainstack.operating_truth"
    finally:
        provider.shutdown()


def test_operating_context_prefers_explicit_operating_truth_over_continuity_fallback(tmp_path):
    provider = _make_provider(
        tmp_path,
        "operating-truth-precedence",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="workspace-a",
    )
    try:
        store = provider._store
        assert store is not None
        store.conn.execute(
            """
            INSERT INTO continuity_events (
                session_id, turn_number, kind, content, source, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "operating-truth-precedence",
                1,
                "tier2_summary",
                "Old continuity summary should not win.",
                "test",
                json.dumps({}, ensure_ascii=True, sort_keys=True),
                "2026-04-19T00:00:00Z",
                "2026-04-19T00:00:00Z",
            ),
        )
        store.conn.execute(
            """
            INSERT INTO continuity_events (
                session_id, turn_number, kind, content, source, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "operating-truth-precedence",
                1,
                "decision",
                "Old continuity decision should not win.",
                "test",
                json.dumps({}, ensure_ascii=True, sort_keys=True),
                "2026-04-19T00:00:00Z",
                "2026-04-19T00:00:00Z",
            ),
        )
        store.conn.commit()

        provider.prefetch(_operating_truth_text(), session_id="operating-truth-precedence")
        snapshot = store.get_operating_context_snapshot(
            principal_scope_key=provider._principal_scope_key,
            session_id="operating-truth-precedence",
        )

        assert snapshot["active_work_summary"] == "Phase 35 operating truth rollout"
        assert "Old continuity summary should not win." not in snapshot["active_work_summary"]
        assert snapshot["open_decisions"] == [
            "Whether owner-first retrieval should consult operating truth before continuity fallback"
        ]
    finally:
        provider.shutdown()


def test_owner_first_operating_retrieval_surfaces_next_step_for_operating_query(tmp_path):
    provider = _make_provider(
        tmp_path,
        "operating-truth-query",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="workspace-a",
    )
    try:
        provider.prefetch(_operating_truth_text(), session_id="operating-truth-query")
        packet = build_working_memory_packet(
            provider._store,
            query="Mi a következő lépés most?",
            session_id="operating-truth-query",
            principal_scope_key=provider._principal_scope_key,
            timezone_name=provider._user_timezone,
            profile_match_limit=provider._profile_match_limit,
            continuity_recent_limit=provider._continuity_recent_limit,
            continuity_match_limit=provider._continuity_match_limit,
            transcript_match_limit=provider._transcript_match_limit,
            transcript_char_budget=provider._transcript_char_budget,
            graph_limit=provider._graph_match_limit,
            corpus_limit=provider._corpus_match_limit,
            corpus_char_budget=provider._corpus_char_budget,
            operating_match_limit=provider._operating_match_limit,
        )

        assert packet["operating_rows"]
        assert any(str(row.get("record_type") or "") == "next_step" for row in packet["operating_rows"])
        assert "## Brainstack Operating Truth" in packet["block"]
        assert "wire operating records into retrieval and operating context" in packet["block"]
        assert packet["policy"]["operating_limit"] >= 3
    finally:
        provider.shutdown()


def test_unrelated_query_does_not_overinject_operating_truth(tmp_path):
    provider = _make_provider(
        tmp_path,
        "operating-truth-token-discipline",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="workspace-a",
    )
    try:
        provider.prefetch(_operating_truth_text(), session_id="operating-truth-token-discipline")
        packet = build_working_memory_packet(
            provider._store,
            query="What is my name?",
            session_id="operating-truth-token-discipline",
            principal_scope_key=provider._principal_scope_key,
            timezone_name=provider._user_timezone,
            profile_match_limit=provider._profile_match_limit,
            continuity_recent_limit=provider._continuity_recent_limit,
            continuity_match_limit=provider._continuity_match_limit,
            transcript_match_limit=provider._transcript_match_limit,
            transcript_char_budget=provider._transcript_char_budget,
            graph_limit=provider._graph_match_limit,
            corpus_limit=provider._corpus_match_limit,
            corpus_char_budget=provider._corpus_char_budget,
            operating_match_limit=provider._operating_match_limit,
        )

        assert packet["operating_rows"] == []
        assert "## Brainstack Operating Truth" not in packet["block"]
    finally:
        provider.shutdown()
