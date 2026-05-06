from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.active_preference_contract import (
    ACTIVE_PREFERENCE_CARD_SIZE_WARNING_ACK_SLOT,
    DELIVERY_REASON_EXPLICIT_MEMORY_INSPECTION,
    DELIVERY_REASON_PROMPT_REBUILD_AFTER_COMPACTION,
    DELIVERY_REASON_SESSION_START,
)
from brainstack.retrieval import build_system_prompt_projection, render_working_memory_block
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


def _long_rules(count: int = 80) -> list[str]:
    return [
        (
            f"Rule {index:02d} must stay explicit in the active behavior card while preserving "
            "public-safe wording, source authority, compression delivery, and concise agent-facing inspection."
        )
        for index in range(1, count + 1)
    ]


def _realistic_style_rules(count: int = 25) -> list[str]:
    return [
        (
            f"Rule {index:02d} keeps a concrete user-facing communication preference with examples, "
            "negative guidance, and delivery expectations so the card resembles a real explicit rule pack."
        )
        for index in range(1, count + 1)
    ]


def _contract_text(lines: list[str]) -> str:
    return "Public fixture behavior card\n\nRules:\n" + "\n".join(f"- {line}" for line in lines)


def _write_style_rules(provider: BrainstackMemoryProvider, lines: list[str]) -> dict:
    payload = provider.handle_tool_call(
        "brainstack_remember",
        {
            "shelf": "profile",
            "stable_key": "preference.public_fixture_response_style",
            "category": "style_preference",
            "content": _contract_text(lines),
            "source_role": "user",
            "authority_class": "profile",
            "confidence": 0.99,
            "metadata": {"target_slot": "preference.public_fixture_response_style"},
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
        projection = provider.behavior_policy_trace()["system_prompt_block"]["projection"]

        _assert_full_card(block, lines)
        assert STYLE_CONTRACT_SLOT not in projection["rendered_profile_keys"]
        assert STYLE_CONTRACT_SLOT in projection["hidden_profile_keys"]
        assert trace["delivery_reason"] == DELIVERY_REASON_SESSION_START
        assert trace["delivery_status"] == "delivered_full"
        assert trace["active_preference_contract_delivered_full"] is True
        assert trace["compiled_rule_count"] == 25
        assert trace["source_rule_count"] == 25
        assert trace["source_stable_key"] == STYLE_CONTRACT_SLOT
        assert trace["source_lane"] == "profile_style_contract"
        assert trace["read_only_projection"] is True
        assert trace["source_profile_stable_key"] == "preference.public_fixture_response_style"
        assert trace["generic_profile_fallback_status"] == "supplemental_source_profile_suppressed"
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


def test_default_budget_delivers_realistic_twenty_five_rule_card(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        lines = _realistic_style_rules()
        receipt = _write_style_rules(provider, lines)
        assert receipt["style_contract_materialization"]["status"] == "materialized"
        assert receipt["style_contract_materialization"]["rule_count"] == 25

        block = provider.system_prompt_block()
        trace = provider.behavior_policy_trace()["system_prompt_block"]["active_preference_contract_delivery"]

        _assert_full_card(block, lines)
        assert trace["delivery_status"] == "delivered_full"
        assert trace["compiled_rule_count"] == 25
        assert trace["source_rule_count"] == 25
        assert trace["omitted_or_compacted_rule_count"] == 0
        warning = provider.behavior_policy_trace()["system_prompt_block"]["projection"][
            "active_preference_delivery_inspect"
        ]["active_card_size_warning"]
        assert warning["status"] == "ok"
        assert warning["should_warn_user"] is False
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
        assert delivery["source_profile_stable_key"] == "preference.public_fixture_response_style"
        assert delivery["generic_profile_fallback_status"] == "supplemental_source_profile_suppressed"
        assert delivery["supplemental_profile_behavior_source_suppressed"] is True
        assert delivery["extra_suppressed_behavior_profile_source_count"] == 0
        assert delivery["suppressed_behavior_sources_prompt_rendered"] is False
        assert delivery["behavior_card_authority_status"] == "canonical_card_delivered_full"
        assert delivery["agent_safe_repair_action"] == "none"
        assert delivery["agent_safe_repair_requires_explicit_user_rules"] is False
        assert delivery["trace_safe"] is True
        assert delivery["raw_private_text_in_trace"] is False
        assert lines[0] not in json.dumps(delivery, ensure_ascii=False)
    finally:
        provider.shutdown()


def test_active_behavior_card_suppresses_legacy_profile_behavior_sources(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        lines = _rules()
        _write_style_rules(provider, lines)
        assert provider._store is not None
        scope = provider._principal_scope_key
        provider._store.upsert_profile_item(
            stable_key="identity:public_fixture_name",
            category="identity",
            content="The public fixture user's handle is ExampleUser.",
            source="user_explicit",
            confidence=0.99,
            metadata={"principal_scope_key": scope},
        )
        provider._store.upsert_profile_item(
            stable_key="style_no_smileys",
            category="style_preference",
            content="Never use smileys or emoji.",
            source="brainstack_remember:profile",
            confidence=0.98,
            metadata={"principal_scope_key": scope},
        )
        provider._store.upsert_profile_item(
            stable_key="preference.public_fixture_legacy_response_style",
            category="communication_style",
            content="Use direct Hungarian Discord style and never use em dash.",
            source="brainstack_remember:profile",
            confidence=0.98,
            metadata={"principal_scope_key": scope},
        )
        provider._store.upsert_profile_item(
            stable_key="preference:communication_style",
            category="preference",
            content="Answer in Hungarian in Discord context unless the user asks otherwise.",
            source="brainstack_remember:profile",
            confidence=0.98,
            metadata={"principal_scope_key": scope},
        )

        projection = build_system_prompt_projection(
            provider._store,
            profile_limit=8,
            principal_scope_key=scope,
            session_id="behavior-card-session",
        )
        block = str(projection["block"])
        trace = projection["active_preference_delivery_trace"]

        assert "# Brainstack Active User Preference Contract" in block
        assert "The public fixture user's handle is ExampleUser." in block
        assert "Never use smileys or emoji." not in block
        assert "Use direct Hungarian Discord style" not in block
        assert "Answer in Hungarian in Discord context" not in block
        assert trace["supplemental_profile_behavior_source_suppressed"] is True
        assert trace["suppressed_behavior_profile_source_count"] >= 3
        assert trace["extra_suppressed_behavior_profile_source_count"] >= 2
        delivery = projection["active_preference_delivery_inspect"]
        assert delivery["behavior_card_authority_status"] == "canonical_card_delivered_full_with_suppressed_legacy_sources"
        assert delivery["agent_safe_repair_action"] == "inspect_active_card_before_claiming_legacy_sources_are_integrated"
    finally:
        provider.shutdown()


def test_profile_behavior_source_does_not_render_without_active_card(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        scope = provider._principal_scope_key
        provider._store.upsert_profile_item(
            stable_key="identity:public_fixture_name",
            category="identity",
            content="The public fixture user's handle is ExampleUser.",
            source="user_explicit",
            confidence=0.99,
            metadata={"principal_scope_key": scope},
        )
        provider._store.upsert_profile_item(
            stable_key="style_no_smileys",
            category="style_preference",
            content="Never use smileys or emoji.",
            source="brainstack_remember:profile",
            confidence=0.98,
            metadata={"principal_scope_key": scope},
        )

        projection = build_system_prompt_projection(
            provider._store,
            profile_limit=8,
            principal_scope_key=scope,
            session_id="behavior-card-session",
        )
        block = str(projection["block"])
        trace = projection["active_preference_delivery_trace"]

        assert "# Brainstack Active User Preference Contract" not in block
        assert "The public fixture user's handle is ExampleUser." in block
        assert "Never use smileys or emoji." not in block
        assert trace["active_preference_contract_delivered"] is False
        assert trace["supplemental_profile_behavior_source_suppressed"] is True
        assert trace["suppressed_behavior_profile_source_count"] == 1
        delivery = projection["active_preference_delivery_inspect"]
        assert delivery["behavior_card_authority_status"] == "behavior_sources_suppressed_no_active_card"
        assert delivery["agent_safe_repair_action"] == "ask_user_for_explicit_style_contract_then_write_with_brainstack_remember"
        assert delivery["agent_safe_repair_requires_explicit_user_rules"] is True
    finally:
        provider.shutdown()


def test_working_memory_packet_does_not_render_legacy_profile_behavior_sources(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        lines = _rules()
        _write_style_rules(provider, lines)
        assert provider._store is not None
        scope = provider._principal_scope_key
        provider._store.upsert_profile_item(
            stable_key="identity:public_fixture_name",
            category="identity",
            content="The public fixture user's handle is ExampleUser.",
            source="user_explicit",
            confidence=0.99,
            metadata={"principal_scope_key": scope},
        )
        provider._store.upsert_profile_item(
            stable_key="style_no_decorative_symbols",
            category="style_preference",
            content="Never render decorative symbols from a legacy profile row.",
            source="brainstack_remember:profile",
            confidence=0.98,
            metadata={"principal_scope_key": scope},
        )
        provider._store.upsert_profile_item(
            stable_key=ACTIVE_PREFERENCE_CARD_SIZE_WARNING_ACK_SLOT,
            category="operating_preference",
            content="The user accepted the current active behavior-card size warning cadence.",
            source="brainstack_remember:profile",
            confidence=0.99,
            metadata={
                "principal_scope_key": scope,
                "source_role": "user",
                "acknowledged_token_estimate": 1000,
            },
        )
        system_substrate = build_system_prompt_projection(
            provider._store,
            profile_limit=0,
            principal_scope_key=scope,
            session_id="behavior-card-session",
        )
        packet_block = render_working_memory_block(
            policy={},
            profile_items=provider._store.list_profile_items(limit=16, principal_scope_key=scope),
            task_rows=[],
            matched=[],
            recent=[],
            transcript_rows=[],
            graph_rows=[],
            corpus_rows=[],
            operating_rows=[],
            system_substrate=system_substrate,
        )

        assert "The public fixture user's handle is ExampleUser." in packet_block
        assert "Never render decorative symbols from a legacy profile row." not in packet_block
        assert "accepted the current active behavior-card size" not in packet_block
    finally:
        provider.shutdown()


def test_communication_style_profile_write_materializes_canonical_card_for_agent_repair(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        lines = _rules()
        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "profile",
                    "stable_key": "preference.public_fixture_communication_style",
                    "category": "communication_style",
                    "content": _contract_text(lines),
                    "source_role": "user",
                    "authority_class": "profile",
                    "confidence": 0.99,
                    "metadata": {"target_slot": "preference.public_fixture_communication_style"},
                },
            )
        )

        assert receipt["status"] == "committed"
        assert receipt["style_contract_materialization"]["status"] == "materialized"
        assert receipt["style_contract_materialization"]["active_card_mutated"] is True
        assert receipt["style_contract_materialization"]["agent_safe_status"] == "canonical_active_card_materialized"
        assert receipt["style_contract_materialization"]["agent_safe_repair_action"] == "none"
        assert receipt["style_contract_materialization"]["rule_count"] == 25
        block = provider.system_prompt_block()
        trace = provider.behavior_policy_trace()["system_prompt_block"]["active_preference_contract_delivery"]

        _assert_full_card(block, lines)
        assert trace["source_profile_stable_key"] == "preference.public_fixture_communication_style"
        assert trace["delivery_status"] == "delivered_full"
    finally:
        provider.shutdown()


def test_non_behavior_profile_write_with_rule_like_markdown_does_not_materialize_card(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        lines = _rules()
        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "profile",
                    "stable_key": "work_context.public_fixture_release_plan",
                    "category": "work_context",
                    "content": _contract_text(lines),
                    "source_role": "user",
                    "authority_class": "profile",
                    "confidence": 0.99,
                    "metadata": {"target_slot": "work_context.public_fixture_release_plan"},
                },
            )
        )

        assert receipt["status"] == "committed"
        assert receipt["style_contract_materialization"]["status"] == "skipped"
        assert receipt["style_contract_materialization"]["reason_code"] == "not_behavior_style_profile_capture"
        assert receipt["style_contract_materialization"]["active_card_mutated"] is False
        assert receipt["style_contract_materialization"]["agent_safe_status"] == "source_profile_only_not_behavior_card"
        assert (
            receipt["style_contract_materialization"]["agent_safe_repair_action"]
            == "write_exact_structured_style_rule_pack_if_user_wants_behavior_card"
        )
        assert provider._store is not None
        assert provider._store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        ) is None
        block = provider.system_prompt_block()
        assert "# Brainstack Active User Preference Contract" not in block
        assert "# Brainstack Profile" in block
    finally:
        provider.shutdown()


def test_native_rule_like_memory_write_without_style_authority_does_not_materialize_card(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        lines = _rules()
        provider.on_memory_write(
            "add",
            "user",
            _contract_text(lines),
            metadata={"host_receipt_id": "host:public_fixture_rule_like_context"},
        )

        assert provider._store is not None
        assert provider._store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        ) is None
        assert "# Brainstack Active User Preference Contract" not in provider.system_prompt_block()
    finally:
        provider.shutdown()


def test_collapsed_style_summary_does_not_patch_existing_active_card(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        old_lines = [
            "Keep replies concise.",
            "Use plain language.",
            "Report tool-backed certainty.",
        ]
        _write_style_rules(provider, old_lines)
        collapsed_summary = (
            "User response style rules: start directly without polite openers; answer yes or no first; "
            "avoid excessive formatting; avoid decorative symbols; avoid vague authority claims; "
            "do not inflate significance; keep terms stable; use simple verbs; avoid passive voice; "
            "do not close with generic positive lines; keep short chat rhythm; be specific; avoid formal phrasing; "
            "answer in a casual direct style; state confidence for tool output; avoid too many headings; "
            "write content bullets, not label templates; apply a final internal filter before replying; "
            "also preserve many additional user wording constraints that must not be merged into one rule."
        )

        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "profile",
                    "stable_key": "preference.public_fixture_collapsed_style_summary",
                    "category": "style_preference",
                    "content": collapsed_summary,
                    "source_role": "user",
                    "authority_class": "profile",
                    "confidence": 0.99,
                    "metadata": {"target_slot": "preference.public_fixture_collapsed_style_summary"},
                },
            )
        )

        assert receipt["status"] == "committed"
        assert receipt["style_contract_materialization"]["status"] == "skipped"
        assert receipt["style_contract_materialization"]["reason_code"] == "not_explicit_style_contract"
        assert receipt["style_contract_materialization"]["active_card_mutated"] is False
        assert receipt["style_contract_materialization"]["agent_safe_status"] == "source_profile_only_not_rule_pack"
        assert (
            receipt["style_contract_materialization"]["agent_safe_repair_action"]
            == "ask_user_for_exact_structured_rule_pack_or_use_rule_id_correction_surface"
        )
        assert provider._store is not None
        canonical = provider._store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        )
        assert canonical is not None
        assert collapsed_summary not in canonical["content"]
        for line in old_lines:
            assert line in canonical["content"]
    finally:
        provider.shutdown()


def test_single_style_preference_does_not_patch_existing_card_without_correction_surface(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        old_lines = [
            "Use formal wording.",
            "Keep replies concise.",
            "Report tool-backed certainty.",
        ]
        _write_style_rules(provider, old_lines)
        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "profile",
                    "stable_key": "preference.public_fixture_single_style_preference",
                    "category": "style_preference",
                    "content": "Use plain language.",
                    "source_role": "user",
                    "authority_class": "profile",
                    "confidence": 0.99,
                    "metadata": {"target_slot": "preference.public_fixture_single_style_preference"},
                },
            )
        )

        assert receipt["status"] == "committed"
        assert receipt["style_contract_materialization"]["status"] == "skipped"
        assert receipt["style_contract_materialization"]["reason_code"] == "not_explicit_style_contract"
        assert receipt["style_contract_materialization"]["active_card_mutated"] is False
        assert receipt["style_contract_materialization"]["agent_safe_status"] == "source_profile_only_not_rule_pack"
        assert provider._store is not None
        canonical = provider._store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        )
        assert canonical is not None
        assert "Use formal wording." in canonical["content"]
        assert "Use plain language." not in canonical["content"]
    finally:
        provider.shutdown()


def test_one_rule_style_contract_addition_does_not_replace_existing_active_card(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        old_lines = [
            "Use formal wording.",
            "Keep replies concise.",
            "Report tool-backed certainty.",
        ]
        _write_style_rules(provider, old_lines)
        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "profile",
                    "stable_key": "preference.public_fixture_single_rule_addition",
                    "category": "style_preference",
                    "content": "User style contract rule-pack addition:\n- Use plain language.",
                    "source_role": "user",
                    "authority_class": "profile",
                    "confidence": 0.99,
                    "metadata": {"target_slot": "preference.public_fixture_single_rule_addition"},
                },
            )
        )

        assert receipt["status"] == "committed"
        assert receipt["style_contract_materialization"]["status"] == "skipped"
        assert (
            receipt["style_contract_materialization"]["reason_code"]
            == "would_shrink_existing_style_contract"
        )
        assert receipt["style_contract_materialization"]["active_card_mutated"] is False
        assert (
            receipt["style_contract_materialization"]["agent_safe_status"]
            == "source_profile_only_would_shrink_active_card"
        )
        assert provider._store is not None
        canonical = provider._store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        )
        assert canonical is not None
        assert "Use formal wording." in canonical["content"]
        assert "Use plain language." not in canonical["content"]
    finally:
        provider.shutdown()


def test_user_supplied_patch_authorization_metadata_cannot_patch_active_card(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        old_lines = [
            "Use formal wording.",
            "Keep replies concise.",
            "Report tool-backed certainty.",
        ]
        _write_style_rules(provider, old_lines)
        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "profile",
                    "stable_key": "preference.public_fixture_untrusted_patch_auth",
                    "category": "style_preference",
                    "content": "Use plain language.",
                    "source_role": "user",
                    "authority_class": "profile",
                    "confidence": 0.99,
                    "metadata": {
                        "target_slot": "preference.public_fixture_untrusted_patch_auth",
                        "style_contract_patch_authorized": True,
                    },
                },
            )
        )

        assert receipt["status"] == "committed"
        assert receipt["style_contract_materialization"]["status"] == "skipped"
        assert receipt["style_contract_materialization"]["reason_code"] == "not_explicit_style_contract"
        assert receipt["style_contract_materialization"]["active_card_mutated"] is False
        assert provider._store is not None
        canonical = provider._store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        )
        assert canonical is not None
        assert "Use formal wording." in canonical["content"]
        assert "Use plain language." not in canonical["content"]
        assert "style_contract_patch_authorized" not in str(canonical.get("metadata") or {})
    finally:
        provider.shutdown()


def test_rule_id_behavior_policy_correction_updates_active_card(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        old_lines = [
            "Use formal wording.",
            "Keep replies concise.",
            "Report tool-backed certainty.",
        ]
        _write_style_rules(provider, old_lines)
        snapshot = provider.apply_behavior_policy_correction(
            rule_id="rules-01",
            replacement_text="Use plain language.",
        )

        assert snapshot is not None
        assert provider._store is not None
        canonical = provider._store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        )
        assert canonical is not None
        assert "Use formal wording." not in canonical["content"]
        assert "Use plain language." in canonical["content"]
        block = provider.system_prompt_block()
        assert "Use plain language." in block
    finally:
        provider.shutdown()


def test_large_active_behavior_card_warns_without_prompt_spam(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        lines = _long_rules()
        _write_style_rules(provider, lines)
        assert provider._store is not None

        projection = build_system_prompt_projection(
            provider._store,
            profile_limit=4,
            principal_scope_key=provider._principal_scope_key,
            session_id="behavior-card-session",
            behavior_contract_char_budget=20000,
        )

        block = str(projection["block"])
        warning = projection["active_preference_delivery_inspect"]["active_card_size_warning"]

        assert warning["status"] == "warn"
        assert warning["severity"] == "medium"
        assert warning["should_warn_user"] is True
        assert warning["estimated_token_count"] >= warning["warning_token_threshold"]
        assert warning["agent_safe_ack_write"]["stable_key"] == ACTIVE_PREFERENCE_CARD_SIZE_WARNING_ACK_SLOT
        assert warning["agent_safe_ack_write"]["requires_explicit_user_confirmation"] is True
        assert warning["agent_safe_ack_write"]["source_role"] == "user"
        assert warning["agent_safe_ack_write"]["authority_class"] == "profile"
        assert warning["agent_safe_ack_write"]["metadata"]["acknowledged_token_estimate"] == warning["estimated_token_count"]
        assert warning["agent_safe_warning"] not in block
    finally:
        provider.shutdown()


def test_large_active_behavior_card_ack_suppresses_until_size_doubles(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        lines = _long_rules()
        _write_style_rules(provider, lines)
        assert provider._store is not None

        first_projection = build_system_prompt_projection(
            provider._store,
            profile_limit=4,
            principal_scope_key=provider._principal_scope_key,
            session_id="behavior-card-session",
            behavior_contract_char_budget=20000,
        )
        token_estimate = first_projection["active_preference_delivery_inspect"]["active_card_size_warning"][
            "estimated_token_count"
        ]
        assert token_estimate > 0

        provider._store.upsert_profile_item(
            stable_key=ACTIVE_PREFERENCE_CARD_SIZE_WARNING_ACK_SLOT,
            category="operating_preference",
            content="The user accepted the current active behavior-card size warning cadence.",
            source="brainstack_remember:profile",
            confidence=0.99,
            metadata={
                "principal_scope_key": provider._principal_scope_key,
                "source_role": "user",
                "acknowledged_token_estimate": token_estimate,
                "acknowledgement_scope": "active_preference_card_size_warning",
            },
        )
        acknowledged_projection = build_system_prompt_projection(
            provider._store,
            profile_limit=4,
            principal_scope_key=provider._principal_scope_key,
            session_id="behavior-card-session",
            behavior_contract_char_budget=20000,
        )
        acknowledged_warning = acknowledged_projection["active_preference_delivery_inspect"]["active_card_size_warning"]
        assert acknowledged_warning["status"] == "acknowledged_until_growth_doubles"
        assert acknowledged_warning["should_warn_user"] is False
        assert acknowledged_warning["rewarn_token_threshold"] >= token_estimate * 2
        assert "accepted the current active behavior-card size" not in str(acknowledged_projection["block"])

        provider._store.upsert_profile_item(
            stable_key=ACTIVE_PREFERENCE_CARD_SIZE_WARNING_ACK_SLOT,
            category="operating_preference",
            content="The user accepted a smaller prior active behavior-card size warning cadence.",
            source="brainstack_remember:profile",
            confidence=0.99,
            metadata={
                "principal_scope_key": provider._principal_scope_key,
                "source_role": "user",
                "acknowledged_token_estimate": max(1, token_estimate // 3),
                "acknowledgement_scope": "active_preference_card_size_warning",
            },
        )
        growth_projection = build_system_prompt_projection(
            provider._store,
            profile_limit=4,
            principal_scope_key=provider._principal_scope_key,
            session_id="behavior-card-session",
            behavior_contract_char_budget=20000,
        )
        growth_warning = growth_projection["active_preference_delivery_inspect"]["active_card_size_warning"]
        assert growth_warning["status"] == "warn_growth_since_user_ack"
        assert growth_warning["should_warn_user"] is True
    finally:
        provider.shutdown()
