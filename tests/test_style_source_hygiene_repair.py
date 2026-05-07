from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.maintenance import STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS
from brainstack.retrieval import build_system_prompt_projection
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
        "style-source-hygiene-session",
        platform="test",
        user_id="public-user",
        agent_identity="agent-style-source-hygiene",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _contract_text() -> str:
    rules = [f"Rule {index:02d} must remain in the canonical behavior card." for index in range(1, 27)]
    return "Public fixture behavior contract\n\nRules:\n" + "\n".join(f"- {rule}" for rule in rules)


def _seed_dirty_live_shape(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    scope = provider._principal_scope_key
    provider.handle_tool_call(
        "brainstack_remember",
        {
            "shelf": "profile",
            "stable_key": "preference.public_fixture_style_rule_pack",
            "category": "style_preference",
            "content": _contract_text(),
            "source_role": "user",
            "authority_class": "profile",
            "confidence": 0.99,
            "metadata": {"target_slot": "preference.public_fixture_style_rule_pack"},
        },
    )
    provider._store.upsert_profile_item(
        stable_key="identity:public_fixture_user",
        category="identity",
        content="The public fixture user's handle is ExampleUser.",
        source="user_explicit",
        confidence=0.99,
        metadata={"principal_scope_key": scope},
    )
    provider._store.upsert_profile_item(
        stable_key="style_no_decorative_symbols",
        category="style_preference",
        content="Legacy source row: never render decorative symbols.",
        source="brainstack_remember:profile",
        confidence=0.98,
        metadata={"principal_scope_key": scope},
    )
    provider._store.upsert_profile_item(
        stable_key="preference.public_fixture_old_communication_style",
        category="communication_style",
        content="Legacy source row: use direct chat style.",
        source="brainstack_remember:profile",
        confidence=0.98,
        metadata={"principal_scope_key": scope},
    )
    provider._store.upsert_profile_item(
        stable_key="preference:communication_style",
        category="preference",
        content="Legacy source row: keep replies plain.",
        source="tier2:session_end_flush",
        confidence=0.8,
        metadata={
            "principal_scope_key": scope,
            "truth_write_permit": {
                "permit_id": "permit:test:legacy-style-source",
                "write_path_class": "legacy_fixture",
                "source_authority": "user",
                "allowed_shelves": ["profile"],
                "allowed_slots": ["preference:communication_style"],
            },
        },
    )


def test_style_source_hygiene_dry_run_reports_legacy_sources_without_mutation(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        _seed_dirty_live_shape(provider)
        assert provider._store is not None
        before = provider._store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        )
        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_consolidate",
                {"apply": False, "maintenance_class": STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS},
            )
        )

        candidate = next(
            item
            for item in receipt["dry_run"]["candidates"]
            if item["maintenance_class"] == STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS
        )
        after = provider._store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        )
        assert candidate["candidate_count"] == 4
        assert before == after
    finally:
        provider.shutdown()


def test_style_source_hygiene_apply_requires_explicit_user_request(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        _seed_dirty_live_shape(provider)
        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_consolidate",
                {"apply": True, "maintenance_class": STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS},
            )
        )

        assert receipt["status"] == "rejected"
        assert "explicit_user_request_required" in receipt["no_op_reasons"]
    finally:
        provider.shutdown()


def test_style_source_hygiene_demotes_sources_and_preserves_agent_facing_card(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        _seed_dirty_live_shape(provider)
        assert provider._store is not None
        before = provider._store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        )
        assert before is not None

        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_consolidate",
                {
                    "apply": True,
                    "maintenance_class": STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS,
                    "explicit_user_request": True,
                },
            )
        )

        result = receipt["changes"][0]["result"]
        after = provider._store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        )
        projection = build_system_prompt_projection(
            provider._store,
            profile_limit=8,
            principal_scope_key=provider._principal_scope_key,
            session_id="style-source-hygiene-session",
        )
        block = str(projection["block"])

        assert receipt["status"] == "ok"
        assert result["status"] == "applied"
        assert result["demoted_count"] == 4
        assert result["remaining_candidate_count"] == 0
        assert result["final_state_proof"]["canonical_card_unchanged"] is True
        assert result["final_state_proof"]["canonical_rule_count_unchanged"] is True
        assert result["final_state_proof"]["behavior_contract_rows_created"] == 0
        assert result["final_state_proof"]["compiled_behavior_policy_rows_created"] == 0
        assert result["backup_created"] is True
        assert result["backup_ref"].endswith(".bak")
        assert result["backup_path"] == ""
        assert before == after
        assert "# Brainstack Active User Preference Contract" in block
        assert "Rule 26 must remain in the canonical behavior card." in block
        assert "The public fixture user's handle is ExampleUser." in block
        assert "Legacy source row" not in block
        assert json.dumps(result, ensure_ascii=False).find("Legacy source row") == -1
    finally:
        provider.shutdown()
