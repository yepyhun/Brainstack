# ruff: noqa: E402
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location("phase30_operating_context_host_import_shims", _host_shims_path)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider
from brainstack.db import BrainstackStore
from brainstack.retrieval import build_system_prompt_block
from brainstack.style_contract import STYLE_CONTRACT_SLOT


def _scope(platform: str, user_id: str) -> dict[str, object]:
    principal_scope = {
        "platform": platform,
        "user_id": user_id,
        "agent_identity": "assistant-main",
        "agent_workspace": "discord-main",
    }
    principal_scope_key = "|".join(f"{key}:{value}" for key, value in principal_scope.items())
    return {
        "principal_scope": principal_scope,
        "principal_scope_key": principal_scope_key,
    }


def _seed_operating_context(store: BrainstackStore, *, principal_scope_key: str, scope: dict[str, object], session_id: str) -> None:
    store.upsert_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        category="preference",
        content=(
            "User style contract\n\n"
            "Nyelvi minták:\n"
            "- Always respond in Hungarian.\n"
            "- Do not use emojis."
        ),
        source="test",
        confidence=0.96,
        metadata=scope,
    )
    store.upsert_profile_item(
        stable_key="shared_work:brainstack",
        category="shared_work",
        content="We are turning Brainstack into an always-on second brain for Hermes Assistant.",
        source="test",
        confidence=0.9,
        metadata=scope,
    )
    store.add_continuity_event(
        session_id=session_id,
        turn_number=4,
        kind="tier2_summary",
        content="Current work focuses on the always-on Brainstack operating-context slice.",
        source="test",
        metadata=scope,
    )
    store.add_continuity_event(
        session_id=session_id,
        turn_number=4,
        kind="decision",
        content="Brainstack remains context-only for tasks and reminders.",
        source="test",
        metadata=scope,
    )
    store.record_continuity_snapshot_state(
        session_id=session_id,
        turn_number=4,
        kind="tier2_batch",
        message_count=2,
        input_message_count=1,
        digest="abc123",
    )


def test_operating_context_snapshot_derives_existing_work_decisions_and_boundaries(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])
    session_id = "session-operating-context"

    _seed_operating_context(store, principal_scope_key=principal_scope_key, scope=scope, session_id=session_id)

    snapshot = store.get_operating_context_snapshot(
        principal_scope_key=principal_scope_key,
        session_id=session_id,
    )

    assert snapshot["behavior_policy"]["active"] is True
    assert snapshot["active_work_summary"] == "Current work focuses on the always-on Brainstack operating-context slice."
    assert snapshot["open_decisions"] == ["Brainstack remains context-only for tasks and reminders."]
    assert snapshot["session_state"]["active"] is True
    assert snapshot["external_owner_pointers"] == []
    assert snapshot["stable_profile_entries"][0]["category"] == "shared_work"


def test_system_prompt_block_includes_bounded_operating_context_without_behavior_duplication(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])
    session_id = "session-operating-context-block"

    _seed_operating_context(store, principal_scope_key=principal_scope_key, scope=scope, session_id=session_id)

    block = build_system_prompt_block(
        store,
        profile_limit=6,
        principal_scope_key=principal_scope_key,
        session_id=session_id,
    )

    assert "# Brainstack Active Communication Contract" in block
    assert "# Brainstack Operating Context" in block
    assert "Current work focuses on the always-on Brainstack operating-context slice." in block
    assert "Brainstack remains context-only for tasks and reminders." in block
    assert "Reminders, scheduling, and task truth stay with native owners" in block
    assert block.count("# Brainstack Active Communication Contract") == 1


def test_provider_exposes_operating_context_snapshot_and_trace(tmp_path):
    db_path = tmp_path / "brainstack.db"
    provider = BrainstackMemoryProvider()
    provider._config["db_path"] = str(db_path)
    provider.initialize(
        "session-30-0",
        user_id="user-a",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )
    try:
        scope = _scope("discord", "user-a")
        principal_scope_key = str(scope["principal_scope_key"])
        _seed_operating_context(
            provider._store,
            principal_scope_key=principal_scope_key,
            scope=scope,
            session_id="session-30-0",
        )

        prompt_block = provider.system_prompt_block()
        assert "# Brainstack Operating Context" in prompt_block

        snapshot = provider.operating_context_snapshot()
        assert snapshot is not None
        assert snapshot["session_state"]["active"] is True
        assert snapshot["open_decisions"] == ["Brainstack remains context-only for tasks and reminders."]

        trace = provider.operating_context_trace()
        assert trace is not None
        assert trace["system_prompt_block"]["section_present"] is True
        assert trace["system_prompt_block"]["active_work_present"] is True
    finally:
        provider.shutdown()


def test_operating_context_ignores_communication_preference_rows_as_runtime_owner(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])
    session_id = "session-operating-context-filter"

    store.upsert_profile_item(
        stable_key="preference:response_language",
        category="preference",
        content="Always respond in Hungarian.",
        source="test",
        confidence=0.95,
        metadata=scope,
    )
    store.add_continuity_event(
        session_id=session_id,
        turn_number=1,
        kind="tier2_summary",
        content="Current work focuses on Brainstack prompt composition.",
        source="test",
        metadata=scope,
    )
    store.record_continuity_snapshot_state(
        session_id=session_id,
        turn_number=1,
        kind="tier2_batch",
        message_count=2,
        input_message_count=1,
        digest="xyz",
    )

    snapshot = store.get_operating_context_snapshot(
        principal_scope_key=principal_scope_key,
        session_id=session_id,
    )

    assert snapshot["stable_profile_entries"] == []
    block = build_system_prompt_block(
        store,
        profile_limit=6,
        principal_scope_key=principal_scope_key,
        session_id=session_id,
    )
    assert "# Brainstack Operating Context" in block
    assert "[preference] Always respond in Hungarian." not in block
