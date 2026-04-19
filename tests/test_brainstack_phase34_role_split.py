# ruff: noqa: E402
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location(
    "phase34_role_split_host_import_shims",
    _host_shims_path,
)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider
from brainstack.behavior_policy import render_compiled_behavior_policy_section
from brainstack.db import BrainstackStore
from brainstack.retrieval import render_working_memory_block
from brainstack.style_contract import STYLE_CONTRACT_SLOT


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
        "User style contract\n\n"
        "rules:\n"
        "1. Always respond in Hungarian.\n"
        "2. Do not use emoji.\n"
        "3. Do not use em dash punctuation.\n"
        "4. Do not use markdown bold.\n"
        "5. Use a warm, romantic, highly expressive tone.\n"
        "6. Ask a playful follow-up question in every reply.\n"
    )


def test_ordinary_turn_contract_section_uses_pinned_invariant_subset(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    store.upsert_behavior_contract(
        category="preference",
        content=_style_contract_text(),
        source="test",
        confidence=1.0,
        metadata={"principal_scope_key": "discord:user-1"},
    )
    compiled = store.get_compiled_behavior_policy(principal_scope_key="discord:user-1")

    assert compiled is not None
    section = render_compiled_behavior_policy_section(
        compiled["policy"],
        title="## Brainstack Active Communication Contract",
        mode="ordinary_turn",
    )

    assert "bounded ordinary-turn invariant subset" in section
    assert "Always respond in Hungarian." in section
    assert "Do not use emoji." in section
    assert "Do not use markdown bold." in section
    assert "warm, romantic, highly expressive tone" not in section
    assert "playful follow-up question in every reply" not in section


def test_style_contract_route_renders_canonical_contract_separately(tmp_path):
    provider = _make_provider(tmp_path, "style-recall")
    try:
        provider.prefetch(_style_contract_text(), session_id="style-recall")
        store = provider._store
        assert store is not None
        compiled = store.get_compiled_behavior_policy(principal_scope_key=provider._principal_scope_key)
        style_row = store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        )

        block = render_working_memory_block(
            policy={
                "mode": "balanced",
                "provenance_mode": "compact",
                "confidence_band": "high",
                "tool_avoidance_allowed": True,
                "tool_avoidance_reason": "test",
                "show_policy": False,
                "show_graph_history": False,
                "style_contract_char_budget": 2400,
                "compiled_behavior_policy": compiled["policy"] if compiled else None,
            },
            route_mode="style_contract",
            profile_items=[style_row] if style_row else [],
            task_rows=[],
            matched=[],
            recent=[],
            transcript_rows=[],
            graph_rows=[],
            corpus_rows=[],
        )

        assert "## Brainstack Canonical Behavior Contract" in block
        assert "exact contract truth" in block
        assert "warm, romantic, highly expressive tone" in block
        assert "playful follow-up question in every reply" in block
        assert "## Brainstack Active Communication Contract" not in block
    finally:
        provider.shutdown()
