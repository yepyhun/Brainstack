# ruff: noqa: E402
"""Targeted regression tests for phase 30.4 task and commitment truth resolution."""

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location(
    "phase30_4_host_import_shims",
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
    provider = BrainstackMemoryProvider(
        config={
            "db_path": str(Path(tmp_path) / "brainstack.db"),
            "user_timezone": "Europe/Budapest",
        }
    )
    provider.initialize(session_id, hermes_home=str(tmp_path), timezone="Europe/Budapest", **init_kwargs)
    return provider


def test_prefetch_commits_structured_task_records_with_truthful_receipt(tmp_path):
    provider = _make_provider(
        tmp_path,
        "task-capture",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )
    try:
        block = provider.prefetch(
            "Mai feladatom: kaját főzni.\n\nEsetleg bevásárolni\nÉs németet tanulni!",
            session_id="task-capture",
        )
        trace = provider.memory_operation_trace()
        store = provider._store
        assert store is not None
        rows = store.list_task_items(
            principal_scope_key=provider._principal_scope_key,
            statuses=("open",),
            limit=10,
        )

        assert "## Brainstack Memory Operation Receipt" in block
        assert trace is not None
        assert trace["last_write_receipt"]["status"] == "committed"
        assert trace["last_write_receipt"]["owner"] == "brainstack.task_memory"
        assert trace["last_write_receipt"]["write_class"] == "task_memory"
        assert trace["last_write_receipt"]["item_count"] == 3
        assert len(rows) == 3
        assert any(bool(row["optional"]) for row in rows)
    finally:
        provider.shutdown()


def test_task_lookup_after_reset_uses_committed_task_records_and_disables_corpus(tmp_path):
    provider = _make_provider(
        tmp_path,
        "task-writer",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )
    try:
        provider.prefetch(
            "Mai feladatom: kaját főzni.\n\nEsetleg bevásárolni\nÉs németet tanulni!",
            session_id="task-writer",
        )
    finally:
        provider.shutdown()

    provider = _make_provider(
        tmp_path,
        "task-reader",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )
    try:
        block = provider.prefetch("Mik a mai napi feladataim?", session_id="task-reader")
        store = provider._store
        assert store is not None
        packet = build_working_memory_packet(
            store,
            query="Mik a mai napi feladataim?",
            session_id="task-reader",
            principal_scope_key=provider._principal_scope_key,
            timezone_name="Europe/Budapest",
            profile_match_limit=4,
            continuity_recent_limit=4,
            continuity_match_limit=4,
            transcript_match_limit=2,
            transcript_char_budget=560,
            graph_limit=6,
            corpus_limit=4,
            corpus_char_budget=700,
        )

        assert "## Brainstack Task Memory" in block
        assert "kaját főzni" in block
        assert "németet tanulni" in block
        assert "Use the committed Brainstack task records below as authoritative" in block
        assert packet["policy"]["corpus_limit"] == 0
        assert len(packet["task_rows"]) == 3
        assert packet["corpus_rows"] == []
    finally:
        provider.shutdown()
