# ruff: noqa: E402
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location("phase30_5_host_import_shims", _host_shims_path)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider
from brainstack.control_plane import build_working_memory_packet
from brainstack.db import BrainstackStore
from brainstack.style_contract import (
    STYLE_CONTRACT_SLOT,
    build_style_contract_from_text,
    list_style_contract_rules,
)


def _sync_user_turn(provider: BrainstackMemoryProvider, content: str, *, session_id: str) -> None:
    provider.sync_turn(content, "", session_id=session_id)


def test_style_contract_commits_into_first_class_behavior_contract_storage(tmp_path):
    provider = BrainstackMemoryProvider(config={"db_path": str(tmp_path / "brainstack.db")})
    provider.initialize(
        "session-behavior-contract",
        hermes_home=str(tmp_path),
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )

    try:
        _sync_user_turn(
            provider,
            (
                "User style contract\n\n"
                "content:\n"
                "1. konkrét tények\n"
                "2. ne használj emojit\n\n"
                "language:\n"
                "3. mindig magyarul válaszolj"
            ),
            session_id="session-behavior-contract",
        )
        store = provider._store
        assert store is not None

        row = store.get_behavior_contract(principal_scope_key=provider._principal_scope_key)
        compat_row = store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        )
        compiled = store.get_compiled_behavior_policy(principal_scope_key=provider._principal_scope_key)

        assert row is not None
        assert compat_row is not None
        assert row["storage_key"].startswith("behavior_contract::")
        assert row["revision_number"] == 1
        assert compat_row["storage_key"] == row["storage_key"]
        assert compiled is not None
        assert compiled["policy"]["source_storage_key"] == row["storage_key"]
        assert all(
            str(item.get("stable_key") or "") != STYLE_CONTRACT_SLOT
            for item in store.list_profile_items(limit=20, principal_scope_key=provider._principal_scope_key)
        )

        trace = provider.memory_operation_trace()
        assert trace is not None
        receipt = trace["last_write_receipt"]
        assert receipt["owner"] == "brainstack.behavior_contract"
        assert receipt["behavior_contract_revision"] == 1
        assert receipt["behavior_contract_storage_key"] == row["storage_key"]
    finally:
        provider.shutdown()


def test_behavior_policy_correction_creates_new_behavior_contract_revision(tmp_path):
    provider = BrainstackMemoryProvider(config={"db_path": str(tmp_path / "brainstack.db")})
    provider.initialize(
        "session-behavior-correction",
        hermes_home=str(tmp_path),
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )

    try:
        _sync_user_turn(
            provider,
            (
                "User style contract\n\n"
                "rules:\n"
                "1. mindig magyarul válaszolj\n"
                "2. ne használj emojit\n"
                "3. ne használj em dash-t"
            ),
            session_id="session-behavior-correction",
        )
        store = provider._store
        assert store is not None
        first = store.get_behavior_contract(principal_scope_key=provider._principal_scope_key)
        assert first is not None
        first_rule = list_style_contract_rules(raw_text=first["content"], metadata=first["metadata"])[0]

        snapshot = provider.apply_behavior_policy_correction(
            rule_id=first_rule["rule_id"],
            replacement_text="mindig magyarul és tömören válaszolj",
        )

        second = store.get_behavior_contract(principal_scope_key=provider._principal_scope_key)
        assert snapshot is not None
        assert second is not None
        assert second["id"] != first["id"]
        assert second["revision_number"] == first["revision_number"] + 1
        assert second["parent_revision_id"] == first["id"]
        assert snapshot["raw_contract"]["storage_key"] == second["storage_key"]
        assert snapshot["compiled_policy"]["source_storage_key"] == second["storage_key"]

        old_row = store.conn.execute(
            "SELECT status FROM behavior_contracts WHERE id = ?",
            (int(first["id"]),),
        ).fetchone()
        assert old_row is not None
        assert str(old_row["status"]) == "superseded"
    finally:
        provider.shutdown()


def test_multi_message_style_contract_fragments_converge_before_canonical_commit(tmp_path):
    provider = BrainstackMemoryProvider(config={"db_path": str(tmp_path / "brainstack.db")})
    provider.initialize(
        "session-behavior-fragments",
        hermes_home=str(tmp_path),
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )

    try:
        first_fragment = (
            "konkrét tények - nem puffasztom fel a jelentőséget\n"
            "konkrét forrás - nem használok homályos hivatkozásokat"
        )
        second_fragment = (
            "emoji tilos - nem használok emojit\n"
            "em dash helyett kötőjel - sima hyphen-minus jelet használok"
        )

        _sync_user_turn(provider, first_fragment, session_id="session-behavior-fragments")
        _sync_user_turn(provider, second_fragment, session_id="session-behavior-fragments")

        store = provider._store
        assert store is not None
        row = store.get_behavior_contract(principal_scope_key=provider._principal_scope_key)
        assert row is not None
        rules = list_style_contract_rules(raw_text=row["content"], metadata=row["metadata"])
        assert len(rules) == 4
        assert any("emoji tilos" in str(rule.get("text") or "") for rule in rules)
        assert any("konkrét tények" in str(rule.get("text") or "") for rule in rules)

        trace = provider.memory_operation_trace()
        assert trace is not None
        receipt = trace["last_write_receipt"]
        assert receipt["owner"] == "brainstack.behavior_contract"
        assert receipt["rule_count"] == 4
        assert receipt["fragment_count"] == 2
    finally:
        provider.shutdown()


def test_lower_quality_tier2_behavior_contract_cannot_supersede_existing_tier2_contract(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    try:
        metadata = {
            "principal_scope_key": "platform:discord|user_id:user-1|agent_identity:assistant-main|agent_workspace:discord-main",
            "principal_scope": {
                "platform": "discord",
                "user_id": "user-1",
                "agent_identity": "assistant-main",
                "agent_workspace": "discord-main",
            },
        }
        full_contract = build_style_contract_from_text(
            raw_text=(
                "User style contract\n\n"
                "rules:\n"
                "1. mindig magyarul válaszolj\n"
                "2. ne használj emojit\n"
                "3. ne használj em dash-t\n"
                "4. maradj tömör"
            ),
            source="tier2_llm",
            metadata=metadata,
        )
        assert full_contract is not None
        first_id = store.upsert_behavior_contract(
            stable_key=STYLE_CONTRACT_SLOT,
            category=str(full_contract["category"]),
            content=str(full_contract["content"]),
            source=str(full_contract["source"]),
            confidence=float(full_contract["confidence"]),
            metadata=dict(full_contract["metadata"]),
        )

        partial_contract = build_style_contract_from_text(
            raw_text="User style contract\n\nrules:\n1. mindig magyarul válaszolj",
            source="tier2_llm",
            metadata=metadata,
        )
        assert partial_contract is not None
        second_id = store.upsert_behavior_contract(
            stable_key=STYLE_CONTRACT_SLOT,
            category=str(partial_contract["category"]),
            content=str(partial_contract["content"]),
            source=str(partial_contract["source"]),
            confidence=float(partial_contract["confidence"]),
            metadata=dict(partial_contract["metadata"]),
        )

        row = store.get_behavior_contract(principal_scope_key=str(metadata["principal_scope_key"]))
        assert row is not None
        assert first_id == second_id == int(row["id"])
        assert row["revision_number"] == 1
        rules = list_style_contract_rules(raw_text=row["content"], metadata=row["metadata"])
        assert len(rules) == 4
    finally:
        store.close()


def test_style_contract_recall_fails_closed_without_committed_contract(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    try:
        principal_scope_key = "platform:discord|user_id:user-1|agent_identity:assistant-main|agent_workspace:discord-main"
        metadata = {
            "principal_scope_key": principal_scope_key,
            "principal_scope": {
                "platform": "discord",
                "user_id": "user-1",
                "agent_identity": "assistant-main",
                "agent_workspace": "discord-main",
            },
        }
        store.upsert_profile_item(
            stable_key="preference:response_language",
            category="preference",
            content="Hungarian",
            source="test",
            confidence=0.9,
            metadata=metadata,
        )
        packet = build_working_memory_packet(
            store,
            query="Give me the full style contract rule list.",
            session_id="style-recall-missing",
            principal_scope_key=principal_scope_key,
            profile_match_limit=8,
            continuity_recent_limit=4,
            continuity_match_limit=4,
            transcript_match_limit=4,
            transcript_char_budget=320,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
            route_resolver=lambda query: {"mode": "style_contract", "reason": "test"},
        )

        assert packet["routing"]["requested_mode"] == "style_contract"
        assert packet["routing"]["fallback_used"] is True
        assert "No committed full behavior contract is stored" in packet["block"]
        assert "Always respond in Hungarian." not in packet["block"]
        assert all(
            str(row.get("stable_key") or "") != "preference:response_language"
            for row in packet["profile_items"]
        )
    finally:
        store.close()
