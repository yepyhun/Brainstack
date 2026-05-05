from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.active_preference_contract import (
    DELIVERY_REASON_EXPLICIT_MEMORY_INSPECTION,
    DELIVERY_REASON_PROMPT_REBUILD_AFTER_COMPACTION,
    DELIVERY_REASON_SESSION_START,
)
from brainstack.style_contract import STYLE_CONTRACT_SLOT


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "behavior-card-session",
        platform="test",
        user_id="user",
        agent_identity="agent-behavior-card",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _rules(count: int = 25) -> list[str]:
    return [f"Rule {index:02d} must survive behavior-card delivery." for index in range(1, count + 1)]


def _contract_text(lines: list[str]) -> str:
    return "LauraTom behavior card\n\nRules:\n" + "\n".join(f"- {line}" for line in lines)


def _write_style_rules(provider: BrainstackMemoryProvider, lines: list[str]) -> dict:
    payload = provider.handle_tool_call(
        "brainstack_remember",
        {
            "shelf": "profile",
            "stable_key": "preference.discord_response_style_plain_hungarian_2026_05_04",
            "category": "style_preference",
            "content": _contract_text(lines),
            "source_role": "user",
            "authority_class": "profile",
            "confidence": 0.99,
            "metadata": {"target_slot": "preference.discord_response_style"},
        },
    )
    return json.loads(payload)


def _assert_full_card(block: str, lines: list[str]) -> None:
    assert "# Brainstack Active User Preference Contract" in block
    assert "# Brainstack Profile" not in block or lines[-1] not in block.split("# Brainstack Profile", 1)[-1]
    for line in lines:
        assert line in block


def test_session_start_delivers_full_active_behavior_card(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        lines = _rules()
        receipt = _write_style_rules(provider, lines)
        assert receipt["style_contract_materialization"]["status"] == "materialized"

        block = provider.system_prompt_block()
        trace = provider.behavior_policy_trace()["system_prompt_block"]["active_preference_contract_delivery"]

        _assert_full_card(block, lines)
        assert trace["delivery_reason"] == DELIVERY_REASON_SESSION_START
        assert trace["delivery_status"] == "delivered_full"
        assert trace["active_preference_contract_delivered_full"] is True
        assert trace["compiled_rule_count"] == 25
        assert trace["source_rule_count"] == 25
        assert trace["source_stable_key"] == STYLE_CONTRACT_SLOT
        assert trace["source_lane"] == "profile_style_contract"
        assert trace["read_only_projection"] is True
        assert trace["source_profile_stable_key"] == "preference.discord_response_style_plain_hungarian_2026_05_04"
        assert trace["generic_profile_fallback_status"] == "supplemental_source_profile_present"
        assert provider._store is not None
        assert provider._store.conn.execute("select count(*) from behavior_contracts").fetchone()[0] == 0
        assert provider._store.conn.execute("select count(*) from compiled_behavior_policies").fetchone()[0] == 0
    finally:
        provider.shutdown()


def test_compression_rebuild_delivers_same_full_active_behavior_card(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        lines = _rules()
        _write_style_rules(provider, lines)
        _assert_full_card(provider.system_prompt_block(), lines)

        provider.on_turn_start(4, "Please remember the behavior-card delivery test.")
        provider.on_pre_compress(
            [
                {"role": "user", "content": "Start a long test conversation."},
                {"role": "assistant", "content": "Acknowledged."},
                {"role": "user", "content": "Now compact the context."},
            ]
        )
        block = provider.system_prompt_block()
        trace = provider.behavior_policy_trace()["system_prompt_block"]["active_preference_contract_delivery"]

        _assert_full_card(block, lines)
        assert trace["delivery_reason"] == DELIVERY_REASON_PROMPT_REBUILD_AFTER_COMPACTION
        assert trace["delivery_status"] == "delivered_full"
        assert trace["active_preference_contract_delivered_full"] is True
        assert trace["compiled_rule_count"] == 25
        assert trace["prompt_rebuild_id"]
        assert trace["compaction_event_id"]
    finally:
        provider.shutdown()


def test_brainstack_inspect_reports_active_card_delivery_without_private_rule_text(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        lines = _rules()
        _write_style_rules(provider, lines)

        inspect = json.loads(
            provider.handle_tool_call("brainstack_inspect", {"query": "active behavior card delivery status"})
        )
        delivery = inspect["report"]["active_preference_delivery"]

        assert delivery["delivery_reason"] == DELIVERY_REASON_EXPLICIT_MEMORY_INSPECTION
        assert delivery["delivery_status"] == "delivered_full"
        assert delivery["delivered_full"] is True
        assert delivery["active_rule_count"] == 25
        assert delivery["source_rule_count"] == 25
        assert delivery["source_stable_key"] == STYLE_CONTRACT_SLOT
        assert delivery["source_lane"] == "profile_style_contract"
        assert delivery["source_profile_stable_key"] == "preference.discord_response_style_plain_hungarian_2026_05_04"
        assert delivery["generic_profile_fallback_status"] == "supplemental_source_profile_present"
        assert delivery["trace_safe"] is True
        assert delivery["raw_private_text_in_trace"] is False
        assert lines[0] not in json.dumps(delivery, ensure_ascii=False)
    finally:
        provider.shutdown()
