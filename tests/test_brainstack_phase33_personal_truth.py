# ruff: noqa: E402
"""Targeted regression tests for phase 33 personal truth hardening."""

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location(
    "phase33_host_import_shims",
    _host_shims_path,
)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider


def _make_provider(tmp_path, session_id: str, **init_kwargs):
    provider = BrainstackMemoryProvider(config={"db_path": str(Path(tmp_path) / "brainstack.db")})
    provider.initialize(session_id, hermes_home=str(tmp_path), **init_kwargs)
    return provider


def _style_contract_text() -> str:
    return (
        "User style contract\n\n"
        "rules:\n"
        "1. Always respond in Hungarian.\n"
        "2. Do not use emojis.\n"
        "3. Capitalize Én, Te, and Ő only when explicitly requested.\n"
    )


def test_personal_scope_fallback_resolves_principal_scoped_profile_item(tmp_path):
    writer = _make_provider(
        tmp_path,
        "scope-writer",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="workspace-a",
    )
    reader = None
    try:
        store = writer._store
        assert store is not None
        metadata = {
            "principal_scope_key": writer._principal_scope_key,
            "principal_scope": dict(writer._principal_scope),
        }
        store.upsert_profile_item(
            stable_key="preference:response_language",
            category="preference",
            content="Always respond in Hungarian.",
            source="test:explicit_preference",
            confidence=0.9,
            metadata=metadata,
        )

        reader = _make_provider(
            tmp_path,
            "scope-reader",
            user_id="user-1",
            platform="discord",
            agent_identity="assistant-main",
            agent_workspace="workspace-b",
        )
        reader_store = reader._store
        assert reader_store is not None

        row = reader_store.get_profile_item(
            stable_key="preference:response_language",
            principal_scope_key=reader._principal_scope_key,
        )

        assert row is not None
        assert row["content"] == "Always respond in Hungarian."
        assert row["principal_scope_key"] == writer._principal_scope_key
    finally:
        if reader is not None:
            reader.shutdown()
        writer.shutdown()


def test_behavior_contract_falls_back_across_workspace_scope_drift(tmp_path):
    writer = _make_provider(
        tmp_path,
        "behavior-writer",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="workspace-a",
    )
    reader = None
    try:
        writer.prefetch(_style_contract_text(), session_id="behavior-writer")
        writer_store = writer._store
        assert writer_store is not None
        committed = writer_store.get_behavior_contract(principal_scope_key=writer._principal_scope_key)
        assert committed is not None

        reader = _make_provider(
            tmp_path,
            "behavior-reader",
            user_id="user-1",
            platform="discord",
            agent_identity="assistant-main",
            agent_workspace="workspace-b",
        )
        reader_store = reader._store
        assert reader_store is not None

        fallback_row = reader_store.get_behavior_contract(principal_scope_key=reader._principal_scope_key)
        compiled = reader_store.get_compiled_behavior_policy(principal_scope_key=reader._principal_scope_key)
        prompt_block = reader.system_prompt_block()

        assert fallback_row is not None
        assert fallback_row["id"] == committed["id"]
        assert fallback_row["principal_scope_key"] == writer._principal_scope_key
        assert compiled is not None
        assert compiled["principal_scope_key"] == writer._principal_scope_key
        assert "# Brainstack Active Communication Contract" in prompt_block
        assert "Always respond in Hungarian." in prompt_block
    finally:
        if reader is not None:
            reader.shutdown()
        writer.shutdown()


def test_short_explicit_correction_patches_canonical_behavior_contract(tmp_path):
    provider = _make_provider(
        tmp_path,
        "short-correction",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="workspace-a",
    )
    try:
        provider.prefetch(_style_contract_text(), session_id="short-correction")
        store = provider._store
        assert store is not None

        first = store.get_behavior_contract(principal_scope_key=provider._principal_scope_key)
        assert first is not None

        block = provider.prefetch(
            "Capitalize Én, Te, and Ő every time you use them.",
            session_id="short-correction",
        )

        second = store.get_behavior_contract(principal_scope_key=provider._principal_scope_key)
        trace = provider.memory_operation_trace()

        assert second is not None
        assert second["revision_number"] == first["revision_number"] + 1
        assert "Capitalize Én, Te, and Ő every time you use them." in second["content"]
        assert "only when explicitly requested" not in second["content"]
        assert "## Brainstack Memory Operation Receipt" in block
        assert trace is not None
        receipt = trace["last_write_receipt"]
        assert receipt["owner"] == "brainstack.behavior_contract"
        assert receipt["patch_rule_count"] == 1
        assert str(receipt["source"]).startswith("prefetch:style_contract_patch")
    finally:
        provider.shutdown()


def test_preference_query_reduces_starvation_without_forcing_full_contract_visibility(tmp_path):
    provider = _make_provider(
        tmp_path,
        "personal-depth",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="workspace-a",
    )
    try:
        provider.prefetch(_style_contract_text(), session_id="personal-depth")

        block = provider.prefetch("What style do I prefer?", session_id="personal-depth")
        policy = provider._last_prefetch_policy

        assert policy is not None
        assert policy["show_authoritative_contract"] is False
        assert policy["transcript_limit"] >= 2
        assert policy["graph_limit"] >= 1
        assert policy["corpus_limit"] >= 1
        assert policy["style_contract_char_budget"] == 0
        assert "## Brainstack Active Communication Contract" in block
        assert "## Brainstack Canonical Behavior Contract" not in block
    finally:
        provider.shutdown()
