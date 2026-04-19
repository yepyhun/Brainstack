# ruff: noqa: E402
"""Targeted regression tests for phase 36 packet collapse and dedupe."""

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location(
    "phase36_host_import_shims",
    _host_shims_path,
)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

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
    provider.initialize(
        session_id,
        hermes_home=str(base),
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="workspace-a",
    )
    return provider


def _sync_user_turn(provider: BrainstackMemoryProvider, content: str, *, session_id: str) -> None:
    provider.sync_turn(content, "", session_id=session_id)


def _style_contract_text() -> str:
    return (
        "User style contract\n\n"
        "rules:\n"
        "1. Always respond in Hungarian.\n"
        "2. Do not use emoji.\n"
        "3. Do not use em dash punctuation.\n"
        "4. Do not use markdown bold.\n"
    )


def test_prefetch_combined_packet_deduplicates_contract_and_profile_against_system_substrate(tmp_path):
    provider = _make_provider(
        tmp_path,
        "phase36-combined-packet",
        profile_prompt_limit=4,
        profile_match_limit=4,
    )
    try:
        store = provider._store
        assert store is not None
        store.upsert_profile_item(
            stable_key="identity:name",
            category="identity",
            content="Tomi",
            source="test",
            confidence=0.95,
            metadata={"principal_scope_key": provider._principal_scope_key},
        )
        _sync_user_turn(provider, _style_contract_text(), session_id="phase36-combined-packet")

        system_block = provider.system_prompt_block()
        working_block = provider.prefetch("Mi a nevem?", session_id="phase36-combined-packet")
        combined = f"{system_block}\n\n{working_block}"

        assert combined.count("Brainstack Active Communication Contract") == 1
        assert combined.count("[identity] Tomi") == 1
        assert "## Brainstack Evidence Priority" not in working_block
    finally:
        provider.shutdown()


def test_prefetch_collapses_recent_continuity_when_matched_rows_already_cover_same_turn(tmp_path):
    provider = _make_provider(
        tmp_path,
        "phase36-continuity-collapse",
        continuity_match_limit=2,
        continuity_recent_limit=2,
        transcript_match_limit=1,
        transcript_char_budget=240,
    )
    try:
        provider.sync_turn(
            "The deployment window stays on Friday at 18:00 UTC after the database migration and Nora owns rollback.",
            "Understood. Friday 18:00 UTC stays reserved and Nora owns rollback.",
            session_id="phase36-continuity-collapse",
        )

        block = provider.prefetch(
            "What is the deployment window after the database migration and who owns rollback?",
            session_id="phase36-continuity-collapse",
        )

        assert "## Brainstack Continuity Match" in block
        assert "## Brainstack Recent Continuity" not in block
        assert "Friday at 18:00 UTC" in block
        assert "Nora" in block
    finally:
        provider.shutdown()
