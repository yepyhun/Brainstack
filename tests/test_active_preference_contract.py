from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.active_preference_contract import (
    CONTRACT_STATUS_ACTIVE,
    CONTRACT_STATUS_DEGRADED,
    CONTRACT_STATUS_EMPTY,
    DELIVERY_REASON_CONTEXT_COMPACTION_REBUILD,
    build_active_preference_contract,
    build_active_preference_delivery_trace,
    build_active_preference_inspect_payload,
)
from brainstack.db import BrainstackStore
from brainstack.retrieval import build_system_prompt_projection
from brainstack.style_contract import STYLE_CONTRACT_SLOT, list_style_contract_rules


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(
        str(tmp_path / "brainstack.sqlite3"),
        graph_backend="sqlite",
        corpus_backend="sqlite",
    )
    store.open()
    return store


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "active-contract-session",
        platform="test",
        user_id="user",
        agent_identity="agent-active-contract",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _rule_lines(count: int) -> list[str]:
    return [f"Rule {index:02d} must be preserved in the active behavior card." for index in range(1, count + 1)]


def _style_contract_text(lines: list[str], *, title: str = "LauraTom style contract") -> str:
    return f"{title}\n\nRules:\n" + "\n".join(f"- {line}" for line in lines)


def _commit_style_contract(store: BrainstackStore, *, scope: str, lines: list[str], source: str = "user_explicit") -> None:
    content = "Communication Rules\n\nRules\n" + "\n".join(f"- {line}" for line in lines)
    store.upsert_behavior_contract(
        stable_key=STYLE_CONTRACT_SLOT,
        category="style_contract",
        content=content,
        source=source,
        confidence=0.98,
        metadata={
            "principal_scope_key": scope,
            "style_contract_title": "Communication Rules",
            "style_contract_sections": [{"heading": "Rules", "lines": lines}],
            "memory_write_receipt_id": f"receipt:{scope}:style",
        },
    )


def test_active_preference_contract_compiles_from_committed_behavior_contract(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        scope = "principal:active-contract"
        _commit_style_contract(
            store,
            scope=scope,
            lines=[
                "Always answer in Hungarian.",
                "Do not use emoji.",
                "Use a concise natural tone.",
            ],
        )

        snapshot = store.get_behavior_policy_snapshot(principal_scope_key=scope)
        contract = build_active_preference_contract(snapshot, principal_scope_key=scope)

        assert contract["schema"] == "brainstack.active_preference_contract.v1"
        assert contract["contract_status"] == CONTRACT_STATUS_ACTIVE
        assert contract["principal_scope_key"] == scope
        assert contract["source_receipt_ids"]
        assert contract["source_preference_refs"][0]["revision_number"] == 1
        assert any("Do not use emoji" in rule["text"] for rule in contract["compiled_rules"])
        assert contract["model_facing_default"] is True
        assert contract["trace_safe"] is True
    finally:
        store.close()


def test_system_prompt_projection_delivers_active_contract_without_profile_retrieval(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        scope = "principal:projection-contract"
        _commit_style_contract(store, scope=scope, lines=["Do not use em dash.", "Answer in German."])

        projection = build_system_prompt_projection(
            store,
            profile_limit=0,
            principal_scope_key=scope,
            session_id="session:test",
            include_behavior_contract=True,
            delivery_reason=DELIVERY_REASON_CONTEXT_COMPACTION_REBUILD,
            prompt_rebuild_id="prompt:1",
            compaction_event_id="compact:1",
        )
        block = str(projection["block"])
        trace = projection["active_preference_delivery_trace"]

        assert "# Brainstack Active User Preference Contract" in block
        assert "Do not use em dash" in block
        assert trace["active_preference_contract_available"] is True
        assert trace["active_preference_contract_delivered"] is True
        assert trace["delivery_reason"] == DELIVERY_REASON_CONTEXT_COMPACTION_REBUILD
        assert trace["prompt_rebuild_id"] == "prompt:1"
        assert trace["compaction_event_id"] == "compact:1"
        assert trace["raw_private_text_in_trace"] is False
    finally:
        store.close()


def test_no_active_preference_is_empty_and_not_delivered(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        projection = build_system_prompt_projection(
            store,
            profile_limit=0,
            principal_scope_key="principal:no-preference",
            session_id="session:test",
        )

        assert projection["active_preference_contract"]["contract_status"] == CONTRACT_STATUS_EMPTY
        assert projection["active_preference_delivery_trace"]["active_preference_contract_delivered"] is False
        assert projection["active_preference_delivery_trace"]["drop_or_skip_reason_code"] == "no_active_user_preferences"
        assert "# Brainstack Active User Preference Contract" not in str(projection["block"])
    finally:
        store.close()


def test_overflow_contract_is_degraded_and_inspectable(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        scope = "principal:overflow-contract"
        _commit_style_contract(
            store,
            scope=scope,
            lines=[f"Explicit communication preference number {index} must be preserved." for index in range(1, 18)],
        )
        snapshot = store.get_behavior_policy_snapshot(principal_scope_key=scope)
        contract = build_active_preference_contract(snapshot, principal_scope_key=scope, char_budget=260)
        inspect_payload = build_active_preference_inspect_payload(contract)

        assert contract["contract_status"] == CONTRACT_STATUS_DEGRADED
        assert contract["omitted_or_compacted_rules"]
        assert inspect_payload["overflow_or_compacted"] is True
        assert inspect_payload["active_rule_count"] > 0
        assert inspect_payload["omitted_or_compacted_rules"]
    finally:
        store.close()


def test_multilingual_preferences_are_compiled_without_language_specific_path(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        scope = "principal:multilingual-contract"
        _commit_style_contract(
            store,
            scope=scope,
            lines=[
                "Válaszolj magyarul.",
                "Write in concise English when asked.",
                "Antworte formell auf Deutsch.",
                "用简洁自然的语气回答。",
            ],
        )
        projection = build_system_prompt_projection(
            store,
            profile_limit=0,
            principal_scope_key=scope,
            session_id="session:test",
        )
        block = str(projection["block"])

        assert "Válaszolj magyarul" in block
        assert "concise English" in block
        assert "Antworte formell" in block
        assert "用简洁自然的语气回答" in block
    finally:
        store.close()


def test_assistant_origin_profile_item_does_not_create_active_contract(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        scope = "principal:assistant-origin"
        store.upsert_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            category="style_contract",
            content="Assistant claimed that emoji are forbidden.",
            source="assistant_summary",
            confidence=0.99,
            metadata={"principal_scope_key": scope, "source_role": "assistant"},
        )

        projection = build_system_prompt_projection(
            store,
            profile_limit=4,
            principal_scope_key=scope,
            session_id="session:test",
        )

        assert projection["active_preference_contract"]["contract_status"] == CONTRACT_STATUS_EMPTY
        assert "# Brainstack Active User Preference Contract" not in str(projection["block"])
    finally:
        store.close()


def test_explicit_profile_lane_style_contract_projects_active_contract_without_behavior_rows(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        scope = "principal:profile-lane-contract"
        store.upsert_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            category="style_contract",
            content=(
                "LauraTom Discord Communication Rules\n\n"
                "Rules\n"
                "- Válaszolj alapból magyarul.\n"
                "- Csak akkor válaszolj angolul, ha Laura kifejezetten kéri.\n"
                "- Magyarázz röviden és közérthetően."
            ),
            source="operator_explicit_user_instruction",
            confidence=0.99,
            metadata={
                "principal_scope_key": scope,
                "source_role": "user",
                "memory_write_receipt_id": "operator:style-contract:test",
                "style_contract_title": "LauraTom Discord Communication Rules",
                "style_contract_sections": [
                    {
                        "heading": "Rules",
                        "lines": [
                            "Válaszolj alapból magyarul.",
                            "Csak akkor válaszolj angolul, ha Laura kifejezetten kéri.",
                            "Magyarázz röviden és közérthetően.",
                        ],
                    }
                ],
            },
        )

        projection = build_system_prompt_projection(
            store,
            profile_limit=0,
            principal_scope_key=scope,
            session_id="session:test",
        )
        contract = projection["active_preference_contract"]
        block = str(projection["block"])

        assert contract["contract_status"] == CONTRACT_STATUS_ACTIVE
        assert projection["active_preference_delivery_trace"]["active_preference_contract_delivered"] is True
        assert "Válaszolj alapból magyarul" in block
        assert "Csak akkor válaszolj angolul" in block
        assert store.conn.execute("select count(*) from behavior_contracts").fetchone()[0] == 0
        assert store.conn.execute("select count(*) from compiled_behavior_policies").fetchone()[0] == 0
    finally:
        store.close()


def test_brainstack_remember_user_style_rules_materializes_canonical_active_card(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        store = provider._store
        assert store is not None
        scope = provider._principal_scope_key
        old_lines = ["Old short rule one.", "Old short rule two.", "Old short rule three."]
        new_lines = _rule_lines(25)
        store.upsert_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            category="style_contract",
            content=_style_contract_text(old_lines, title="Old style contract"),
            source="operator_explicit",
            confidence=0.95,
            metadata={
                "principal_scope_key": scope,
                "source_role": "user",
                "memory_write_receipt_id": "old-style-receipt",
                "style_contract_title": "Old style contract",
                "style_contract_sections": [{"heading": "Rules", "lines": old_lines}],
            },
        )

        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "profile",
                    "stable_key": "preference.discord_response_style_plain_hungarian_2026_05_04",
                    "category": "style_preference",
                    "content": _style_contract_text(new_lines),
                    "source_role": "user",
                    "authority_class": "profile",
                    "confidence": 0.99,
                    "metadata": {"target_slot": "preference.discord_response_style"},
                },
            )
        )

        assert receipt["status"] == "committed"
        assert receipt["style_contract_materialization"]["status"] == "materialized"
        assert receipt["style_contract_materialization"]["rule_count"] == 25
        generic = store.get_profile_item(
            stable_key="preference.discord_response_style_plain_hungarian_2026_05_04",
            principal_scope_key=scope,
        )
        canonical = store.get_profile_item(stable_key=STYLE_CONTRACT_SLOT, principal_scope_key=scope)
        assert generic is not None
        assert canonical is not None
        canonical_metadata = canonical["metadata"]
        assert canonical_metadata["source_profile_stable_key"] == "preference.discord_response_style_plain_hungarian_2026_05_04"
        assert canonical_metadata["memory_write_receipt_id"] == receipt["memory_write_receipt"]["receipt_id"]
        assert len(list_style_contract_rules(raw_text=canonical["content"], metadata=canonical_metadata)) == 25
        assert new_lines[-1] in canonical["content"]
        assert old_lines[0] not in canonical["content"]

        snapshot = store.get_behavior_policy_snapshot(principal_scope_key=scope)
        contract = build_active_preference_contract(snapshot, principal_scope_key=scope, char_budget=10000)
        assert contract["contract_status"] == CONTRACT_STATUS_ACTIVE
        assert len(contract["compiled_rules"]) == 25
        assert receipt["memory_write_receipt"]["receipt_id"] in contract["source_receipt_ids"]
        projection = build_system_prompt_projection(
            store,
            profile_limit=0,
            principal_scope_key=scope,
            session_id="session:test",
        )
        assert projection["active_preference_delivery_trace"]["active_preference_contract_delivered"] is True
        assert store.conn.execute("select count(*) from behavior_contracts").fetchone()[0] == 0
        assert store.conn.execute("select count(*) from compiled_behavior_policies").fetchone()[0] == 0
    finally:
        provider.shutdown()


def test_generic_profile_style_text_alone_is_not_active_card_authority(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        scope = "principal:generic-style-only"
        store.upsert_profile_item(
            stable_key="preference.generic_style_memory",
            category="style_preference",
            content=_style_contract_text(_rule_lines(4)),
            source="user_explicit",
            confidence=0.95,
            metadata={"principal_scope_key": scope, "source_role": "user"},
        )

        projection = build_system_prompt_projection(
            store,
            profile_limit=8,
            principal_scope_key=scope,
            session_id="session:test",
        )

        assert projection["active_preference_contract"]["contract_status"] == CONTRACT_STATUS_EMPTY
        assert "# Brainstack Active User Preference Contract" not in str(projection["block"])
        assert store.get_profile_item(stable_key=STYLE_CONTRACT_SLOT, principal_scope_key=scope) is None
    finally:
        store.close()


def test_non_style_brainstack_remember_profile_write_does_not_activate_card(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        store = provider._store
        assert store is not None
        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "profile",
                    "stable_key": "identity:display_name",
                    "category": "identity",
                    "content": "Laura",
                    "source_role": "user",
                    "authority_class": "profile",
                    "confidence": 0.99,
                },
            )
        )

        assert receipt["status"] == "committed"
        assert receipt["style_contract_materialization"]["status"] == "skipped"
        assert store.get_profile_item(stable_key=STYLE_CONTRACT_SLOT, principal_scope_key=provider._principal_scope_key) is None
    finally:
        provider.shutdown()


def test_delivery_trace_has_registered_safe_shape() -> None:
    trace = build_active_preference_delivery_trace(
        {
            "contract_status": CONTRACT_STATUS_ACTIVE,
            "contract_version": "apc:test",
            "source_receipt_ids": ["r1"],
            "compiled_rules": [{"id": "rule-1", "text": "private text stays out of trace"}],
            "omitted_or_compacted_rules": [],
        },
        delivered=True,
        delivery_reason="not_registered",
    )

    assert trace["delivery_reason"] == "session_substrate_rebuilt"
    assert trace["raw_private_text_in_trace"] is False
    assert "private text" not in str(trace)
