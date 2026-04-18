# ruff: noqa: E402
"""Targeted regression tests for phase 30.2 live residual recovery."""

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location(
    "phase30_2_host_import_shims",
    _host_shims_path,
)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack.behavior_policy import compile_behavior_policy, render_compiled_behavior_policy_section
from brainstack.style_contract import (
    STYLE_CONTRACT_SLOT,
    build_style_contract_from_text,
    looks_like_style_contract_teaching,
)
from brainstack import BrainstackMemoryProvider


def _make_provider(tmp_path, session_id: str, **init_kwargs):
    provider = BrainstackMemoryProvider(config={"db_path": str(Path(tmp_path) / "brainstack.db")})
    provider.initialize(session_id, hermes_home=str(tmp_path), **init_kwargs)
    return provider


def test_numbered_rule_pack_is_accepted_as_explicit_style_contract():
    raw_text = (
        "27 szabály:\n"
        "1. Mindig magyarul válaszolj.\n"
        "2. Ne használj emojikat.\n"
        "3. Ne kérdezz vissza feleslegesen.\n"
        "4. Ne használj U+2014 EM DASH karaktert.\n"
        "5. Konkrét tényekkel válaszolj.\n"
    )

    payload = build_style_contract_from_text(raw_text=raw_text, source="prefetch:style_contract")

    assert payload is not None
    assert looks_like_style_contract_teaching(raw_text) is True
    assert payload["slot"] == STYLE_CONTRACT_SLOT
    assert "1. Mindig magyarul válaszolj." not in payload["content"]
    assert "Mindig magyarul válaszolj." in payload["content"]


def test_prefetch_can_activate_structured_style_contract_before_first_answer(tmp_path):
    provider = _make_provider(
        tmp_path,
        "prefetch-style-contract",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )
    try:
        query = (
            "User style contract\n"
            "1. Mindig magyarul válaszolj.\n"
            "2. Ne használj emojikat.\n"
            "3. Ne kérdezz vissza feleslegesen.\n"
        )

        block = provider.prefetch(query, session_id="prefetch-style-contract")
        store = provider._store
        assert store is not None

        row = store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        )
        compiled = store.get_compiled_behavior_policy(principal_scope_key=provider._principal_scope_key)

        assert row is not None
        assert row["source"] == "prefetch:style_contract"
        assert compiled is not None
        assert compiled["policy"]["status"] == "active"
        assert "## Brainstack Active Communication Contract" in block
        assert provider.behavior_policy_trace()["prefetch"]["style_contract_activated_before_prefetch"] is True
    finally:
        provider.shutdown()


def test_weaker_tier2_style_contract_cannot_overwrite_stronger_deterministic_row(tmp_path):
    provider = _make_provider(
        tmp_path,
        "style-precedence",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )
    try:
        deterministic_query = (
            "User style contract\n"
            "1. Mindig magyarul válaszolj.\n"
            "2. Ne használj emojikat.\n"
            "3. Ne kérdezz vissza feleslegesen.\n"
        )
        provider.prefetch(deterministic_query, session_id="style-precedence")
        store = provider._store
        assert store is not None

        weaker_payload = build_style_contract_from_text(
            raw_text=(
                "User style contract\n"
                "- Magyarul válaszolj.\n"
                "- Ne használj emojikat.\n"
                "- Légy kedves.\n"
            ),
            source="tier2_llm",
        )
        assert weaker_payload is not None
        store.upsert_profile_item(
            stable_key=weaker_payload["slot"],
            category=weaker_payload["category"],
            content=weaker_payload["content"],
            source=weaker_payload["source"],
            confidence=float(weaker_payload["confidence"]),
            metadata=weaker_payload["metadata"],
        )

        row = store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        )
        assert row is not None
        assert row["source"] == "prefetch:style_contract"
        assert "Ne kérdezz vissza feleslegesen." in row["content"]
    finally:
        provider.shutdown()


def test_large_policy_marks_projection_degraded_instead_of_overclaiming_enforcement():
    compiled = compile_behavior_policy(
        raw_content=(
            "User style contract\n\n"
            "Nyelvi minták:\n"
            + "\n".join(
                f"- Rule {index}: keep the response concrete and avoid empty filler."
                for index in range(1, 90)
            )
        ),
        char_budget=380,
    )

    assert compiled is not None
    assert compiled["status"] == "degraded"
    assert compiled["no_compile_drop"] is True
    assert compiled["no_projection_drop"] is False
    assert compiled["projection_rule_count"] < compiled["raw_rule_count"]
    assert compiled["omitted_rule_count"] > 0
    assert any(
        entry["projection_status"] == "omitted_due_budget"
        for entry in compiled["coverage"]
    )

    section = render_compiled_behavior_policy_section(
        compiled,
        title="## Brainstack Active Communication Contract",
    )
    assert "Status: degraded." in section


def test_prefetch_surfaces_correction_reinforcement_for_same_session_rule_callout(tmp_path):
    provider = _make_provider(
        tmp_path,
        "session-correction",
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
                "2. Ne használj emojikat.\n"
                "3. Ne írj U+2014 EM DASH karaktert a válaszba.\n"
            ),
        )

        block = provider.prefetch(
            "Amit írtál az első mondatban az nem em dashjel?",
            session_id="session-correction",
        )
        trace = provider.behavior_policy_trace()

        assert "## Brainstack Current Correction Reinforcement" in block
        assert "U+2014 EM DASH" in block
        assert trace["prefetch"]["correction_reinforcement_present"] is True
        assert trace["prefetch"]["correction_reinforcement_mode"] == "session_reinforcement"
    finally:
        provider.shutdown()


def test_hungarian_today_task_query_matches_cross_session_english_continuity_summary(tmp_path):
    writer = _make_provider(
        tmp_path,
        "session-a",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )
    try:
        store = writer._store
        assert store is not None
        store.add_continuity_event(
            session_id="session-a",
            turn_number=1,
            kind="tier2_summary",
            content="User has three tasks for today: cook food, possibly shop, and learn German.",
            source="tier2_summary",
            metadata={"principal_scope_key": writer._principal_scope_key},
        )
    finally:
        writer.shutdown()

    reader = _make_provider(
        tmp_path,
        "session-b",
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )
    try:
        block = reader.prefetch("Mik a mai napi feladataim?", session_id="session-b")
        assert "## Brainstack Continuity Match" in block
        assert "tasks for today" in block
        assert "cook food" in block
    finally:
        reader.shutdown()
