from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.active_preference_contract import build_active_preference_contract
from brainstack.db import BrainstackStore
from brainstack.retrieval import build_system_prompt_projection
from brainstack.style_contract import STYLE_CONTRACT_SLOT


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
        "active-preference-provenance",
        platform="test",
        user_id="user",
        agent_identity="agent-provenance",
        agent_workspace="workspace",
    )
    return provider


def _contract_text() -> str:
    return "LauraTom style contract\n\nRules:\n- Keep provenance labels honest.\n- Do not imply a durable behavior commit."


def test_profile_lane_read_only_projection_does_not_emit_behavior_commit_receipt_label(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "profile",
                    "stable_key": "preference.provenance_style",
                    "category": "style_preference",
                    "content": _contract_text(),
                    "source_role": "user",
                    "authority_class": "profile",
                    "confidence": 0.99,
                    "metadata": {"target_slot": "preference.provenance_style"},
                },
            )
        )
        projection = build_system_prompt_projection(
            provider._store,
            profile_limit=0,
            principal_scope_key=provider._principal_scope_key,
            session_id="session:test",
        )
        contract = projection["active_preference_contract"]
        source_receipts = list(contract["source_receipt_ids"])
        source_ref = contract["source_preference_refs"][0]
        delivery = projection["active_preference_delivery_inspect"]

        assert receipt["style_contract_materialization"]["status"] == "materialized"
        assert receipt["memory_write_receipt"]["receipt_id"] in source_receipts
        assert not any(str(value).startswith("behavior_contract_commit:") for value in source_receipts)
        assert source_ref["source_lane"] == "profile_style_contract"
        assert source_ref["read_only_projection"] is True
        assert delivery["source_lane"] == "profile_style_contract"
        assert delivery["read_only_projection"] is True
        assert delivery["source_stable_key"] == STYLE_CONTRACT_SLOT
        assert provider._store.conn.execute("select count(*) from behavior_contracts").fetchone()[0] == 0
        assert provider._store.conn.execute("select count(*) from compiled_behavior_policies").fetchone()[0] == 0
    finally:
        provider.shutdown()


def test_durable_behavior_contract_keeps_behavior_commit_receipt_label(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        scope = "principal:durable-behavior-contract"
        store.upsert_behavior_contract(
            stable_key=STYLE_CONTRACT_SLOT,
            category="style_contract",
            content=_contract_text(),
            source="user_explicit",
            confidence=0.98,
            metadata={
                "principal_scope_key": scope,
                "style_contract_title": "Communication Rules",
                "style_contract_sections": [
                    {
                        "heading": "Rules",
                        "lines": [
                            "Keep provenance labels honest.",
                            "Do not imply a durable behavior commit.",
                        ],
                    }
                ],
            },
        )

        snapshot = store.get_behavior_policy_snapshot(principal_scope_key=scope)
        contract = build_active_preference_contract(snapshot, principal_scope_key=scope, char_budget=2400)

        assert any(str(value).startswith("behavior_contract_commit:") for value in contract["source_receipt_ids"])
        assert contract["source_preference_refs"][0]["read_only_projection"] is False
        assert contract["source_preference_refs"][0]["source_lane"] == ""
    finally:
        store.close()
