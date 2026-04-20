# ruff: noqa: E402
"""Targeted regression tests for phase 30.3 host/runtime compliance."""

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location(
    "phase30_3_host_import_shims",
    _host_shims_path,
)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider


def _make_provider(tmp_path, session_id: str, **init_kwargs):
    provider = BrainstackMemoryProvider(
        config={
            "db_path": str(Path(tmp_path) / "brainstack.db"),
            "ordinary_reply_output_validation_enabled": True,
        }
    )
    provider.initialize(session_id, hermes_home=str(tmp_path), **init_kwargs)
    return provider


def test_output_contract_repairs_mechanical_violations(tmp_path):
    provider = _make_provider(
        tmp_path,
        "output-contract",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )
    try:
        provider.on_memory_write(
            "add",
            "user",
            (
                "User style contract\n"
                "1. Mindig magyarul válaszolj.\n"
                "2. Ne írj U+2014 EM DASH karaktert a válaszba.\n"
                "3. Ne használj emojikat.\n"
                "4. Boldface tilos.\n"
            ),
        )

        result = provider.validate_assistant_output("Szia — **teszt** 😄")
        trace = provider.behavior_policy_trace()

        assert result is not None
        assert result["changed"] is True
        assert result["content"] == "Szia - teszt "
        assert len(result["repairs"]) == 3
        assert trace["final_output_validation"]["applied"] is True
        assert trace["final_output_validation"]["changed"] is True
        assert trace["final_output_validation"]["repair_count"] == 3
    finally:
        provider.shutdown()


def test_prefetch_remains_read_only_even_when_style_contract_candidate_is_detected(tmp_path):
    provider = _make_provider(
        tmp_path,
        "prefetch-receipt",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )
    try:
        block = provider.prefetch(
            (
                "User style contract\n"
                "1. Mindig magyarul válaszolj.\n"
                "2. Ne használj emojikat.\n"
                "3. Ne kérdezz vissza feleslegesen.\n"
            ),
            session_id="prefetch-receipt",
        )
        trace = provider.memory_operation_trace()

        assert "## Brainstack Memory Operation Receipt" not in block
        assert trace is not None
        assert trace["barrier_clear"] is True
        assert trace["surface"] == "prefetch_lookup"
        assert trace["last_write_receipt"] == {}
    finally:
        provider.shutdown()


def test_on_memory_write_does_not_claim_brainstack_receipt_for_non_bounded_native_mirror(tmp_path):
    provider = _make_provider(
        tmp_path,
        "profile-receipt",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )
    try:
        provider.on_memory_write("add", "user", "Mindig tömör választ kérek.")
        trace = provider.memory_operation_trace()

        assert trace is not None
        assert trace["barrier_clear"] is True
        assert trace["surface"] == "native_profile_mirror"
        assert trace["last_write_receipt"] == {}
        assert "no bounded Brainstack mirror candidates" in trace["note"]
    finally:
        provider.shutdown()


def test_system_prompt_stays_empty_for_ordinary_chat_after_non_bounded_native_write(tmp_path):
    provider = _make_provider(
        tmp_path,
        "prompt-contract",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )
    try:
        provider.on_memory_write("add", "user", "Mindig magyarul válaszolj.")
        block = provider.system_prompt_block()

        assert block == ""
    finally:
        provider.shutdown()


def test_task_lookup_semantics_do_not_overclaim_committed_record(tmp_path):
    provider = _make_provider(
        tmp_path,
        "task-lookup",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )
    try:
        store = provider._store
        assert store is not None
        store.add_continuity_event(
            session_id="task-lookup",
            turn_number=1,
            kind="tier2_summary",
            content="User has three tasks for today: cook food, possibly shop, and learn German.",
            source="tier2_summary",
            metadata={"principal_scope_key": provider._principal_scope_key},
        )

        block = provider.prefetch("Mik a mai napi feladataim?", session_id="task-lookup")

        assert "## Brainstack Lookup Semantics" in block
        assert "Brainstack task memory is the structured owner for this lookup in this runtime." in block
        assert "No committed Brainstack task record matched this lookup." in block
        assert "continuity evidence only" in block
        assert "supporting shelves only: continuity_match" in block
    finally:
        provider.shutdown()
