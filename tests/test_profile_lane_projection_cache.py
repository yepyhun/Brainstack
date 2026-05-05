from __future__ import annotations

from pathlib import Path

import brainstack.storage.profile_store as profile_store_module
from brainstack.active_preference_contract import build_active_preference_contract
from brainstack.db import BrainstackStore
from brainstack.style_contract import STYLE_CONTRACT_SLOT


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(
        str(tmp_path / "brainstack.sqlite3"),
        graph_backend="sqlite",
        corpus_backend="sqlite",
    )
    store.open()
    return store


def _upsert_profile_lane_contract(store: BrainstackStore, *, scope: str, rules: list[str]) -> None:
    store.upsert_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        category="style_contract",
        content="LauraTom behavior card\n\nRules:\n" + "\n".join(f"- {rule}" for rule in rules),
        source="operator_explicit",
        confidence=0.99,
        metadata={
            "principal_scope_key": scope,
            "source_role": "user",
            "memory_write_receipt_id": f"receipt:{scope}",
            "style_contract_title": "LauraTom behavior card",
            "style_contract_sections": [{"heading": "Rules", "lines": rules}],
        },
    )


def test_profile_lane_projection_cache_compiles_once_for_repeated_reads(tmp_path: Path, monkeypatch) -> None:
    store = _open_store(tmp_path)
    calls: list[str] = []
    real_compile = profile_store_module.compile_behavior_policy

    def counted_compile(*args, **kwargs):
        calls.append("compile")
        return real_compile(*args, **kwargs)

    monkeypatch.setattr(profile_store_module, "compile_behavior_policy", counted_compile)
    try:
        scope = "principal:cache-repeat"
        _upsert_profile_lane_contract(
            store,
            scope=scope,
            rules=["Rule one stays cached.", "Rule two stays cached.", "Rule three stays cached."],
        )

        for _ in range(100):
            snapshot = store.get_behavior_policy_snapshot(principal_scope_key=scope)
            contract = build_active_preference_contract(snapshot, principal_scope_key=scope, char_budget=2400)
            assert contract["contract_status"] == "active"
            assert len(contract["compiled_rules"]) == 3

        assert len(calls) == 1
        snapshot = store.get_behavior_policy_snapshot(principal_scope_key=scope)
        cache_trace = snapshot["compiled_policy"]["profile_lane_projection_cache"]
        assert cache_trace["status"] == "hit"
        assert cache_trace["cache_durable"] is False
        assert store.conn.execute("select count(*) from behavior_contracts").fetchone()[0] == 0
        assert store.conn.execute("select count(*) from compiled_behavior_policies").fetchone()[0] == 0
    finally:
        store.close()


def test_profile_lane_projection_cache_invalidates_on_profile_revision_change(tmp_path: Path, monkeypatch) -> None:
    store = _open_store(tmp_path)
    calls: list[str] = []
    real_compile = profile_store_module.compile_behavior_policy

    def counted_compile(*args, **kwargs):
        calls.append("compile")
        return real_compile(*args, **kwargs)

    monkeypatch.setattr(profile_store_module, "compile_behavior_policy", counted_compile)
    try:
        scope = "principal:cache-invalidate"
        _upsert_profile_lane_contract(
            store,
            scope=scope,
            rules=["Rule one stays cached.", "Rule two stays cached."],
        )
        first = store.get_behavior_policy_snapshot(principal_scope_key=scope)
        assert first["compiled_policy"]["profile_lane_projection_cache"]["status"] == "miss"
        assert len(calls) == 1
        second = store.get_behavior_policy_snapshot(principal_scope_key=scope)
        assert second["compiled_policy"]["profile_lane_projection_cache"]["status"] == "hit"
        assert len(calls) == 1

        _upsert_profile_lane_contract(
            store,
            scope=scope,
            rules=["Rule one stays cached.", "Rule two stays cached.", "Rule three invalidates cache."],
        )
        mutated = store.get_behavior_policy_snapshot(principal_scope_key=scope)
        contract = build_active_preference_contract(mutated, principal_scope_key=scope, char_budget=2400)

        assert len(calls) == 2
        assert mutated["compiled_policy"]["profile_lane_projection_cache"]["status"] == "miss"
        assert len(contract["compiled_rules"]) == 3
        assert "Rule three invalidates cache." in contract["projection_text"]
        assert store.conn.execute("select count(*) from behavior_contracts").fetchone()[0] == 0
        assert store.conn.execute("select count(*) from compiled_behavior_policies").fetchone()[0] == 0
    finally:
        store.close()
