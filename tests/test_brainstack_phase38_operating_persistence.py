from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location(
    "phase38_host_import_shims",
    _host_shims_path,
)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider
from brainstack.operating_truth import (  # noqa: E402
    OPERATING_RECORD_CURRENT_COMMITMENT,
    OPERATING_RECORD_NEXT_STEP,
)


def _make_provider(tmp_path: Path, session_id: str) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(config={"db_path": str(tmp_path / "brainstack.db")})
    provider.initialize(
        session_id,
        hermes_home=str(tmp_path),
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="workspace-a",
    )
    return provider


def _sync_user_turn(provider: BrainstackMemoryProvider, content: str, *, session_id: str) -> None:
    provider.sync_turn(content, "", session_id=session_id)


def _operating_truth_text() -> str:
    return (
        "Active work:\n"
        "- Phase 38 operating persistence hardening\n\n"
        "Current commitments:\n"
        "- Keep donor-first architecture intact\n"
        "- Eliminate silent overwrite for multi-item operating truth\n\n"
        "Next steps:\n"
        "- Implement append-safe stable keys\n"
        "- Verify read/write boundary cleanup\n"
    )


def _task_capture_text() -> str:
    return (
        "Tasks for today:\n"
        "- review phase 38 persistence semantics\n"
        "- write the phase 38 verification notes\n"
    )


def test_operating_truth_preserves_multiple_commitments_and_next_steps(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase38-operating-multi")
    try:
        _sync_user_turn(provider, _operating_truth_text(), session_id="phase38-operating-multi")

        store = provider._store
        assert store is not None
        records = store.list_operating_records(
            principal_scope_key=provider._principal_scope_key,
            record_types=(OPERATING_RECORD_CURRENT_COMMITMENT, OPERATING_RECORD_NEXT_STEP),
            limit=10,
        )
        commitments = [row for row in records if row["record_type"] == OPERATING_RECORD_CURRENT_COMMITMENT]
        next_steps = [row for row in records if row["record_type"] == OPERATING_RECORD_NEXT_STEP]

        assert len(commitments) == 2
        assert len({row["stable_key"] for row in commitments}) == 2
        assert len(next_steps) == 2
        assert len({row["stable_key"] for row in next_steps}) == 2

        snapshot = store.get_operating_context_snapshot(
            principal_scope_key=provider._principal_scope_key,
            session_id="phase38-operating-multi",
        )
        assert "Keep donor-first architecture intact" in list(snapshot.get("current_commitments") or [])
        assert "Eliminate silent overwrite for multi-item operating truth" in list(
            snapshot.get("current_commitments") or []
        )
        assert "Implement append-safe stable keys" in list(snapshot.get("next_steps") or [])
        assert "Verify read/write boundary cleanup" in list(snapshot.get("next_steps") or [])
    finally:
        provider.shutdown()


def test_prefetch_operating_lookup_does_not_write_without_explicit_structure(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase38-operating-read-only")
    try:
        block = provider.prefetch("What are we doing right now?", session_id="phase38-operating-read-only")

        store = provider._store
        assert store is not None
        records = store.list_operating_records(
            principal_scope_key=provider._principal_scope_key,
            limit=10,
        )

        assert records == []
        assert "## Brainstack Working Memory Policy" in block
        assert provider._last_write_receipt is None
    finally:
        provider.shutdown()


def test_prefetch_task_lookup_does_not_write_without_explicit_structure(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase38-task-read-only")
    try:
        provider.prefetch("mi a feladatom ma?", session_id="phase38-task-read-only")

        store = provider._store
        assert store is not None
        tasks = store.list_task_items(
            principal_scope_key=provider._principal_scope_key,
            limit=10,
        )

        assert tasks == []
        assert provider._last_write_receipt is None
    finally:
        provider.shutdown()


def test_sync_turn_explicit_task_capture_commits(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase38-task-explicit")
    try:
        _sync_user_turn(provider, _task_capture_text(), session_id="phase38-task-explicit")

        store = provider._store
        assert store is not None
        tasks = store.list_task_items(
            principal_scope_key=provider._principal_scope_key,
            limit=10,
        )

        titles = [str(item["title"]) for item in tasks]
        assert "review phase 38 persistence semantics" in titles
        assert "write the phase 38 verification notes" in titles

        trace = provider.memory_operation_trace()
        assert trace is not None
        receipt = trace["last_write_receipt"]
        assert receipt["owner"] == "brainstack.task_memory"
        assert receipt["write_class"] == "task_memory"
    finally:
        provider.shutdown()
