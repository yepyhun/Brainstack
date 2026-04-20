# ruff: noqa: E402
"""Regression tests for phase 50 host-control de-escalation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location(
    "phase50_host_import_shims",
    _host_shims_path,
)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider  # noqa: E402


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


def _style_contract_text() -> str:
    return (
        "User style contract\n"
        "1. Mindig magyarul válaszolj.\n"
        "2. Ne használj emojikat.\n"
        "3. Ne használj kötőjeles írásjeleket a válaszokban.\n"
        "4. Gondolatonként új sort kezdj.\n"
    )


def test_provider_system_prompt_omits_behavior_contract_by_default(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase50-system-prompt")
    try:
        provider.on_memory_write("add", "user", _style_contract_text())
        block = provider.system_prompt_block()
        assert "# Brainstack Active Communication Contract" not in block
    finally:
        provider.shutdown()


def test_prefetch_ordinary_chat_omits_contract_pressure_by_default(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase50-prefetch")
    try:
        provider.on_memory_write("add", "user", _style_contract_text())
        block = provider.prefetch("Szia! Itt vagy?", session_id="phase50-prefetch")
        trace = provider.behavior_policy_trace()

        assert "## Brainstack Active Communication Contract" not in block
        assert "## Brainstack Current Correction Reinforcement" not in block
        assert trace is not None
        assert trace["prefetch"]["compiled_policy_present_in_packet"] is True
        assert trace["prefetch"]["projection_present_in_block"] is False
        assert trace["prefetch"]["correction_reinforcement_present"] is False
    finally:
        provider.shutdown()


def test_prefetch_explicit_style_recall_still_returns_canonical_contract(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase50-style-recall")
    try:
        provider.on_memory_write("add", "user", _style_contract_text())
        block = provider.prefetch(
            "Emlékszel a 25 szabályra? Mondd el a kommunikációs szabályokat.",
            session_id="phase50-style-recall",
        )
        trace = provider.behavior_policy_trace()

        assert "## Brainstack Canonical Behavior Contract" in block
        assert trace is not None
        assert trace["prefetch"]["route_mode"] == "style_contract"
    finally:
        provider.shutdown()


def test_provider_skips_ordinary_reply_output_validation_by_default(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase50-output-validation")
    try:
        provider.on_memory_write("add", "user", _style_contract_text())
        result = provider.validate_assistant_output("Szia 😊")
        trace = provider.behavior_policy_trace()

        assert result is None
        assert trace is not None
        assert trace["final_output_validation"]["status"] == "skipped"
        assert trace["final_output_validation"]["blocked"] is False
        assert trace["final_output_validation"]["can_ship"] is True
    finally:
        provider.shutdown()
