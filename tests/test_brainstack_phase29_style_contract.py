# ruff: noqa: E402
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location("phase29_style_host_import_shims", _host_shims_path)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack.control_plane import build_working_memory_packet
from brainstack.behavior_policy import (
    BEHAVIOR_POLICY_COMPILER_VERSION,
    compile_behavior_policy,
)
from brainstack.db import BrainstackStore, MIGRATION_COMPILED_BEHAVIOR_POLICY_V2
from brainstack.reconciler import reconcile_tier2_candidates
from brainstack.retrieval import build_system_prompt_block
from brainstack.style_contract import (
    STYLE_CONTRACT_DOC_KIND,
    STYLE_CONTRACT_SLOT,
    apply_style_contract_rule_correction,
    build_style_contract_from_text,
    list_style_contract_rules,
)
from brainstack.tier2_extractor import extract_tier2_candidates
from brainstack import BrainstackMemoryProvider


def _scope(platform: str, user_id: str) -> dict[str, object]:
    principal_scope = {
        "platform": platform,
        "user_id": user_id,
        "agent_identity": "assistant-main",
        "agent_workspace": "discord-main",
    }
    principal_scope_key = "|".join(f"{key}:{value}" for key, value in principal_scope.items())
    return {
        "principal_scope": principal_scope,
        "principal_scope_key": principal_scope_key,
    }


def test_tier2_extractor_normalizes_structured_style_contract_payload():
    def _fake_llm_caller(**kwargs):
        return {
            "content": json.dumps(
                {
                    "profile_items": [],
                    "style_contract": {
                        "title": "User style contract",
                        "summary": "Use the full user-defined rules on demand.",
                        "sections": [
                            {
                                "heading": "Tartalmi minták",
                                "lines": [
                                    "Konkrét tények, nem jelentőségfelfújás",
                                    "Egy konkrét forrás, nem homályos hivatkozások",
                                ],
                            },
                            {
                                "heading": "Nyelvi minták",
                                "lines": [
                                    "Vessző, pont vagy zárójel em dash helyett",
                                    "Emoji tilos",
                                ],
                            },
                        ],
                        "confidence": 0.97,
                    },
                    "states": [],
                    "relations": [],
                    "inferred_relations": [],
                    "typed_entities": [],
                    "temporal_events": [],
                    "continuity_summary": "",
                    "decisions": [],
                }
            )
        }

    extracted = extract_tier2_candidates(
        [{"turn_number": 1, "kind": "turn", "content": "User pasted the full style rule pack."}],
        llm_caller=_fake_llm_caller,
    )

    assert extracted["style_contract"] is not None
    assert extracted["style_contract"]["slot"] == STYLE_CONTRACT_SLOT
    assert "User style contract" in extracted["style_contract"]["content"]
    assert "Tartalmi minták:" in extracted["style_contract"]["content"]
    assert "- Konkrét tények, nem jelentőségfelfújás" in extracted["style_contract"]["content"]


def test_build_style_contract_from_text_requires_structured_rule_pack():
    payload = build_style_contract_from_text(
        raw_text=(
            "User style contract\n\n"
            "Tartalmi minták:\n"
            "- Konkrét tények, nem jelentőségfelfújás\n"
            "- Egy konkrét forrás, nem homályos hivatkozások\n\n"
            "Nyelvi minták:\n"
            "- Nincs hármas szabály"
        ),
        source="test",
    )
    assert payload is not None
    assert payload["slot"] == STYLE_CONTRACT_SLOT
    assert "Tartalmi minták:" in payload["content"]

    assert build_style_contract_from_text(raw_text="I prefer concise answers.", source="test") is None


def test_compile_behavior_policy_emits_first_class_kinds_and_no_silent_drop():
    compiled = compile_behavior_policy(
        raw_content=(
            "User style contract\n\n"
            "Tartalmi minták:\n"
            "- Konkrét tények, nem jelentőségfelfújás\n"
            "- Egy konkrét forrás, nem homályos hivatkozások\n\n"
            "Nyelvi minták:\n"
            "- Vessző, pont, zárójel, em dash helyett\n"
            "- Boldface tilos\n"
            "- Emoji tilos\n\n"
            "Kommunikációs minták:\n"
            "- Köszönésre ne válts át generikus follow-up kérdésre\n"
            "- Szervilis hangnem kötelező\n\n"
            "Töltelék:\n"
            "- Töltelékszövegek röviden\n"
        ),
        char_budget=1200,
    )

    assert compiled is not None
    assert compiled["compiler_version"] == BEHAVIOR_POLICY_COMPILER_VERSION
    assert compiled["raw_rule_count"] == 8
    assert compiled["no_silent_drop"] is True
    assert len(compiled["coverage"]) == compiled["raw_rule_count"]
    assert all(entry["status"] == "compiled_active" for entry in compiled["coverage"])

    kinds = {clause["kind"] for clause in compiled["clauses"]}
    assert "content_policy" in kinds
    assert "question_policy" in kinds
    assert "punctuation_policy" in kinds
    assert "formatting_policy" in kinds
    assert "forbidden_surface_form" in kinds
    assert "tone_policy" in kinds
    assert "verbosity_policy" in kinds

    assert "Content discipline:" in compiled["projection_text"]
    assert "Follow-up behavior:" in compiled["projection_text"]
    assert "Forbidden surface forms:" in compiled["projection_text"]
    assert '"Miben segíthetek?"' in compiled["projection_text"]
    assert "- Emoji tilos" in compiled["projection_text"]


def test_compile_behavior_policy_projection_stays_bounded_with_coverage_for_large_rule_pack():
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
    assert compiled["raw_rule_count"] == 89
    assert len(compiled["coverage"]) == 89
    assert compiled["status"] == "degraded"
    assert compiled["no_projection_drop"] is False
    assert compiled["projection_char_count"] <= 380
    assert compiled["truncated"] is True
    assert compiled["projection_text"].rstrip().endswith("omitted)")


def test_on_memory_write_structured_style_contract_activates_before_next_answer(tmp_path):
    provider = BrainstackMemoryProvider(config={"db_path": str(tmp_path / "brainstack.db")})
    provider.initialize(
        "session-style-write",
        hermes_home=str(tmp_path),
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
                "User style contract\n\n"
                "Tartalmi minták:\n"
                "- Konkrét tények, nem jelentőségfelfújás\n"
                "- Egy konkrét forrás, nem homályos hivatkozások\n\n"
                "Nyelvi minták:\n"
                "- Nincs hármas szabály"
            ),
        )
        store = provider._store
        assert store is not None

        row = store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        )
        compiled = store.get_compiled_behavior_policy(principal_scope_key=provider._principal_scope_key)

        assert row is not None
        assert compiled is not None
        assert compiled["policy"]["status"] == "active"

        prompt_block = provider.system_prompt_block()
        assert "# Brainstack Active Communication Contract" in prompt_block
        assert "User style contract" in prompt_block
        assert "Konkrét tények, nem jelentőségfelfújás" in prompt_block
    finally:
        provider.shutdown()


def test_sync_turn_structured_style_contract_activates_before_next_turn(tmp_path):
    provider = BrainstackMemoryProvider(config={"db_path": str(tmp_path / "brainstack.db")})
    provider.initialize(
        "session-style-sync",
        hermes_home=str(tmp_path),
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )

    try:
        provider.sync_turn(
            (
                "User style contract\n\n"
                "Nyelvi minták:\n"
                "- Mindig magyarul válaszolj\n"
                "- Ne használj emojikat\n\n"
                "Kommunikációs minták:\n"
                "- Köszönésre ne válts át generikus follow-up kérdésre\n"
            ),
            "Megértettem, tartom a szerződést.",
            session_id="session-style-sync",
        )

        store = provider._store
        assert store is not None
        row = store.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=provider._principal_scope_key,
        )
        compiled = store.get_compiled_behavior_policy(principal_scope_key=provider._principal_scope_key)

        assert row is not None
        assert compiled is not None
        assert compiled["policy"]["status"] == "active"
        assert "Follow-up behavior:" in compiled["projection_text"]
        assert '"Miben segíthetek?"' in compiled["projection_text"]

        prompt_block = provider.system_prompt_block()
        assert "# Brainstack Active Communication Contract" in prompt_block
        assert "User style contract" in prompt_block
    finally:
        provider.shutdown()


def test_on_memory_write_non_policy_content_keeps_generic_preference_behavior(tmp_path):
    provider = BrainstackMemoryProvider(config={"db_path": str(tmp_path / "brainstack.db")})
    provider.initialize(
        "session-style-write-generic",
        hermes_home=str(tmp_path),
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )

    try:
        provider.on_memory_write("add", "user", "I prefer concise answers.")
        store = provider._store
        assert store is not None

        compiled = store.get_compiled_behavior_policy(principal_scope_key=provider._principal_scope_key)
        rows = store.list_profile_items(limit=10, principal_scope_key=provider._principal_scope_key)

        assert compiled is None
        assert any(str(row.get("content") or "") == "I prefer concise answers." for row in rows)
        assert all(str(row.get("stable_key") or "") != STYLE_CONTRACT_SLOT for row in rows)
    finally:
        provider.shutdown()


def test_on_memory_write_invalid_contract_does_not_replace_active_policy(tmp_path):
    provider = BrainstackMemoryProvider(config={"db_path": str(tmp_path / "brainstack.db")})
    provider.initialize(
        "session-style-write-failclosed",
        hermes_home=str(tmp_path),
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
                "User style contract\n\n"
                "Tartalmi minták:\n"
                "- Konkrét tények, nem jelentőségfelfújás\n"
                "- Egy konkrét forrás, nem homályos hivatkozások"
            ),
        )
        store = provider._store
        assert store is not None
        first_policy = store.get_compiled_behavior_policy(principal_scope_key=provider._principal_scope_key)
        assert first_policy is not None
        first_hash = first_policy["policy"]["policy_hash"]

        provider.on_memory_write("add", "user", "User style contract")

        second_policy = store.get_compiled_behavior_policy(principal_scope_key=provider._principal_scope_key)
        assert second_policy is not None
        assert second_policy["policy"]["policy_hash"] == first_hash
    finally:
        provider.shutdown()


def test_updating_style_contract_recompiles_policy_with_new_hash_and_coverage(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])

    store.upsert_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        category="preference",
        content=(
            "User style contract\n\n"
            "Nyelvi minták:\n"
            "- Emoji tilos\n"
            "- Boldface tilos"
        ),
        source="test",
        confidence=0.96,
        metadata=scope,
    )
    first = store.get_compiled_behavior_policy(principal_scope_key=principal_scope_key)
    assert first is not None

    store.upsert_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        category="preference",
        content=(
            "User style contract\n\n"
            "Nyelvi minták:\n"
            "- Boldface tilos\n"
            "- Vessző, pont, zárójel, em dash helyett"
        ),
        source="test",
        confidence=0.97,
        metadata=scope,
    )
    second = store.get_compiled_behavior_policy(principal_scope_key=principal_scope_key)
    assert second is not None

    assert first["policy"]["policy_hash"] != second["policy"]["policy_hash"]
    assert first["policy"]["source_contract_hash"] != second["policy"]["source_contract_hash"]
    assert second["policy"]["no_silent_drop"] is True
    assert len(second["policy"]["coverage"]) == second["policy"]["raw_rule_count"]
    assert "Emoji tilos" not in second["projection_text"]
    assert "U+2014 EM DASH" in second["projection_text"]


def test_reconcile_tier2_candidates_upserts_canonical_style_contract_profile_row(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])

    result = reconcile_tier2_candidates(
        store,
        session_id="session-style-a",
        turn_number=3,
        source="tier2:test",
        metadata=scope,
        extracted={
            "style_contract": {
                "title": "User style contract",
                "summary": "Detailed style contract.",
                "sections": [
                    {"heading": "Kommunikációs minták", "lines": ["Chatbot maradványok tilos"]},
                    {"heading": "Stílus minták", "lines": ['"Let\'s dive in" jellegű bejelentések tilos']},
                ],
            }
        },
    )

    row = store.get_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        principal_scope_key=principal_scope_key,
    )
    assert row is not None
    assert "Kommunikációs minták:" in row["content"]
    assert any(action["kind"] == "style_contract" and action["action"] == "ADD" for action in result["actions"])


def test_reconcile_tier2_candidates_accepts_extractor_normalized_style_contract(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])

    def _fake_llm_caller(**kwargs):
        return {
            "content": json.dumps(
                {
                    "profile_items": [],
                    "style_contract": {
                        "title": "27 Communication Rules",
                        "summary": "Detailed multi-section communication pack for Hungarian chat style.",
                        "sections": [
                            {
                                "heading": "tartalmi minták (1-5)",
                                "lines": [
                                    "konkrét tények nem jelentőségfelfújás",
                                    "egy konkrét forrás nem homályos hivatkozások",
                                ],
                            },
                            {
                                "heading": "kommunikációs minták (18-20)",
                                "lines": [
                                    "chatbot maradványok tilos",
                                    "knowledge cutoff disclaimer tilos",
                                ],
                            },
                        ],
                        "confidence": 0.98,
                    },
                    "states": [],
                    "relations": [],
                    "inferred_relations": [],
                    "typed_entities": [],
                    "temporal_events": [],
                    "continuity_summary": "",
                    "decisions": [],
                }
            )
        }

    extracted = extract_tier2_candidates(
        [{"turn_number": 1, "kind": "turn", "content": "User pasted the 27 communication rules."}],
        llm_caller=_fake_llm_caller,
    )

    assert extracted["style_contract"] is not None
    assert extracted["style_contract"]["slot"] == STYLE_CONTRACT_SLOT

    result = reconcile_tier2_candidates(
        store,
        session_id="session-style-normalized",
        turn_number=1,
        source="tier2:test",
        metadata=scope,
        extracted=extracted,
    )

    row = store.get_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        principal_scope_key=principal_scope_key,
    )
    assert row is not None
    assert "27 Communication Rules" in row["content"]
    assert "tartalmi minták (1-5):" in row["content"]
    assert "\n\n" in row["content"]
    assert any(action["kind"] == "style_contract" and action["action"] == "ADD" for action in result["actions"])


def test_tier2_batch_receives_multiline_style_contract_transcript_without_flattening(tmp_path):
    base = Path(tmp_path)
    seen_rows = []

    def _fake_extractor(rows, **kwargs):
        seen_rows.extend(rows)
        return {
            "profile_items": [],
            "style_contract": None,
            "states": [],
            "relations": [],
            "inferred_relations": [],
            "typed_entities": [],
            "temporal_events": [],
            "continuity_summary": "",
            "decisions": [],
        }

    provider = BrainstackMemoryProvider(
        config={
            "db_path": str(base / "brainstack.db"),
            "tier2_batch_turn_limit": 1,
            "_tier2_extractor": _fake_extractor,
        }
    )
    provider.initialize("session-style-batch", hermes_home=str(base), user_id="user-1", platform="discord")

    try:
        provider.sync_turn(
            (
                "tartalmi minták (1-5):\n"
                "konkrét tények nem jelentőségfelfújás\n"
                "egy konkrét forrás nem homályos hivatkozások\n\n"
                "kommunikációs minták (18-20):\n"
                "chatbot maradványok tilos\n"
                "knowledge cutoff disclaimer tilos"
            ),
            "Megvan.",
            session_id="session-style-batch",
        )
        assert provider._wait_for_tier2_worker(timeout=1.0) is True
        assert seen_rows
        content = str(seen_rows[-1].get("content") or "")
        assert "tartalmi minták (1-5):\nkonkrét tények nem jelentőségfelfújás" in content
        assert "\nkommunikációs minták (18-20):\n" in content
        assert "konkrét tények nem jelentőségfelfújás egy konkrét forrás" not in content
    finally:
        provider.shutdown()


def test_style_contract_explicit_recall_uses_canonical_profile_slot_without_leaking_into_ordinary_turns(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])

    store.upsert_profile_item(
        stable_key="preference:response_language",
        category="preference",
        content="Always respond in Hungarian.",
        source="test",
        confidence=0.95,
        metadata=scope,
    )
    store.upsert_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        category="preference",
        content=(
            "User style contract\n\n"
            "Tartalmi minták:\n"
            "- Konkrét tények, nem jelentőségfelfújás\n"
            "- Egy konkrét forrás, nem homályos hivatkozások"
        ),
        source="test",
        confidence=0.96,
        metadata=scope,
    )

    explicit_packet = build_working_memory_packet(
        store,
        query="Do you know the 29 style rules?",
        session_id="session-style-a",
        principal_scope_key=principal_scope_key,
        profile_match_limit=6,
        continuity_recent_limit=2,
        continuity_match_limit=2,
        transcript_match_limit=2,
        transcript_char_budget=500,
        graph_limit=2,
        corpus_limit=2,
        corpus_char_budget=500,
        route_resolver=lambda query: {"mode": "style_contract", "reason": "test"},
    )

    assert explicit_packet["routing"]["applied_mode"] == "style_contract"
    assert [row["stable_key"] for row in explicit_packet["profile_items"]] == [STYLE_CONTRACT_SLOT]
    assert "## Brainstack Canonical Behavior Contract" in explicit_packet["block"]
    assert "User style contract" in explicit_packet["block"]
    assert "Tartalmi minták:" in explicit_packet["block"]
    assert "- Konkrét tények, nem jelentőségfelfújás" in explicit_packet["block"]
    assert "- Egy konkrét forrás, nem homályos hivatkozások" in explicit_packet["block"]
    assert "..." not in explicit_packet["block"].split("## Brainstack Canonical Behavior Contract\n", 1)[1]

    ordinary_packet = build_working_memory_packet(
        store,
        query="Beszélgessünk egy kicsit!",
        session_id="session-style-a",
        principal_scope_key=principal_scope_key,
        profile_match_limit=6,
        continuity_recent_limit=2,
        continuity_match_limit=2,
        transcript_match_limit=2,
        transcript_char_budget=500,
        graph_limit=2,
        corpus_limit=2,
        corpus_char_budget=500,
        route_resolver=lambda query: {"mode": "fact", "reason": "test"},
    )

    assert ordinary_packet["routing"]["applied_mode"] == "fact"
    assert ordinary_packet["policy"]["compiled_behavior_policy"]["status"] == "active"
    assert all(row["stable_key"] != STYLE_CONTRACT_SLOT for row in ordinary_packet["profile_items"])
    assert "## Brainstack Active Communication Contract" in ordinary_packet["block"]
    assert "User style contract" in ordinary_packet["block"]
    assert "## Brainstack Profile Match" not in ordinary_packet["block"]


def test_style_contract_explicit_recall_uses_deterministic_route_without_llm_hint(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])

    store.upsert_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        category="preference",
        content=(
            "User style contract\n\n"
            "Tartalmi minták:\n"
            "- Konkrét tények, nem jelentőségfelfújás\n"
            "- Egy konkrét forrás, nem homályos hivatkozások"
        ),
        source="test",
        confidence=0.96,
        metadata=scope,
    )

    packet = build_working_memory_packet(
        store,
        query="Mondd a 27 szabályt pontosan.",
        session_id="session-style-deterministic",
        principal_scope_key=principal_scope_key,
        profile_match_limit=6,
        continuity_recent_limit=2,
        continuity_match_limit=2,
        transcript_match_limit=2,
        transcript_char_budget=500,
        graph_limit=2,
        corpus_limit=2,
        corpus_char_budget=500,
        route_resolver=lambda query: (_ for _ in ()).throw(RuntimeError("route hint should not run")),
    )

    assert packet["routing"]["applied_mode"] == "style_contract"
    assert packet["routing"]["source"] == "deterministic_style_contract_hint"
    assert [row["stable_key"] for row in packet["profile_items"]] == [STYLE_CONTRACT_SLOT]
    assert "Tartalmi minták:" in packet["block"]
    assert "- Konkrét tények, nem jelentőségfelfújás" in packet["block"]


def test_compiled_behavior_policy_becomes_ordinary_turn_owner(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])

    store.upsert_profile_item(
        stable_key="preference:response_language",
        category="preference",
        content="Always respond in English.",
        source="test",
        confidence=0.95,
        metadata=scope,
    )
    store.upsert_graph_state(
        subject_name="Assistant",
        attribute="writing_style",
        value_text="Use the configured communication style: direct, concrete, natural, and low-fluff.",
        source="test",
        metadata=scope,
        supersede=True,
    )
    store.upsert_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        category="preference",
        content=(
            "User style contract\n\n"
            "Nyelvi minták:\n"
            "- Always respond in Hungarian.\n"
            "- Do not use emojis."
        ),
        source="test",
        confidence=0.96,
        metadata=scope,
    )

    compiled = store.get_compiled_behavior_policy(principal_scope_key=principal_scope_key)
    assert compiled is not None
    assert compiled["policy"]["source_storage_key"].startswith("behavior_contract::")

    prompt_block = build_system_prompt_block(
        store,
        profile_limit=10,
        principal_scope_key=principal_scope_key,
    )
    assert "# Brainstack Active Communication Contract" in prompt_block
    assert "User style contract" in prompt_block
    assert "Always respond in Hungarian." in prompt_block
    assert "Do not use emojis." in prompt_block
    assert "[preference] Always respond in English." not in prompt_block
    assert "Use the configured communication style: direct, concrete, natural, and low-fluff." not in prompt_block

    packet = build_working_memory_packet(
        store,
        query="Magyarázd el ezt a kódot röviden.",
        session_id="session-style-owner",
        principal_scope_key=principal_scope_key,
        profile_match_limit=6,
        continuity_recent_limit=2,
        continuity_match_limit=2,
        transcript_match_limit=2,
        transcript_char_budget=500,
        graph_limit=4,
        corpus_limit=2,
        corpus_char_budget=500,
        route_resolver=lambda query: {"mode": "fact", "reason": "test"},
    )
    assert "## Brainstack Active Communication Contract" in packet["block"]
    assert "Always respond in Hungarian." in packet["block"]
    assert "Do not use emojis." in packet["block"]
    assert "[preference] Always respond in English." not in packet["block"]
    assert "Use the configured communication style: direct, concrete, natural, and low-fluff." not in packet["block"]


def test_behavior_policy_snapshot_exposes_raw_compiled_and_parity(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])

    store.upsert_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        category="preference",
        content=(
            "User style contract\n\n"
            "Nyelvi minták:\n"
            "- Always respond in Hungarian.\n"
            "- Do not use emojis."
        ),
        source="test",
        confidence=0.96,
        metadata=scope,
    )

    snapshot = store.get_behavior_policy_snapshot(principal_scope_key=principal_scope_key)
    assert snapshot["raw_contract"]["present"] is True
    assert snapshot["compiled_policy"]["active"] is True
    assert snapshot["parity"]["source_hash_matches_raw"] is True
    assert snapshot["raw_contract"]["rules"][0]["rule_id"] == "nyelvi-minták-01"


def test_style_contract_rule_listing_and_correction_are_deterministic():
    raw_text = (
        "User style contract\n\n"
        "Nyelvi minták:\n"
        "- Always respond in Hungarian.\n"
        "- Do not use emojis."
    )
    rules = list_style_contract_rules(raw_text=raw_text)
    assert [rule["rule_id"] for rule in rules] == ["nyelvi-minták-01", "nyelvi-minták-02"]

    corrected = apply_style_contract_rule_correction(
        raw_text=raw_text,
        rule_id="nyelvi-minták-02",
        replacement_text="Use emojis only when the user explicitly asks.",
    )
    assert corrected is not None
    assert "Use emojis only when the user explicitly asks." in corrected["content"]
    assert "- Do not use emojis." not in corrected["content"]


def test_provider_exposes_behavior_policy_trace_snapshot_and_correction(tmp_path):
    db_path = tmp_path / "brainstack.db"
    provider = BrainstackMemoryProvider()
    provider._config["db_path"] = str(db_path)
    provider.initialize(
        "session-29-10",
        user_id="user-a",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="discord-main",
    )
    try:
        provider.on_memory_write(
            "add",
            "user",
            (
                "User style contract\n\n"
                "Nyelvi minták:\n"
                "- Always respond in Hungarian.\n"
                "- Do not use emojis."
            ),
        )
        prompt_block = provider.system_prompt_block()
        assert "User style contract" in prompt_block
        packet_block = provider.prefetch("Magyarázd el ezt röviden.")
        assert "Always respond in Hungarian." in packet_block

        snapshot = provider.behavior_policy_snapshot()
        assert snapshot is not None
        assert snapshot["compiled_policy"]["active"] is True

        trace = provider.behavior_policy_trace()
        assert trace is not None
        assert trace["system_prompt_block"]["injected"] is True
        assert trace["prefetch"]["compiled_policy_present_in_packet"] is True

        corrected = provider.apply_behavior_policy_correction(
            rule_id="nyelvi-minták-02",
            replacement_text="Use emojis only when the user explicitly asks.",
        )
        assert corrected is not None
        assert corrected["compiled_policy"]["active"] is True
        assert corrected["parity"]["source_hash_matches_raw"] is True
        refreshed = provider.behavior_policy_snapshot()
        assert refreshed is not None
        assert refreshed["raw_contract"]["rule_count"] == 2
    finally:
        provider.shutdown()


def test_style_contract_deterministic_route_does_not_capture_ordinary_queries(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])

    store.upsert_profile_item(
        stable_key="preference:response_language",
        category="preference",
        content="Always respond in Hungarian.",
        source="test",
        confidence=0.95,
        metadata=scope,
    )
    store.upsert_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        category="preference",
        content=(
            "User style contract\n\n"
            "Tartalmi minták:\n"
            "- Konkrét tények, nem jelentőségfelfújás"
        ),
        source="test",
        confidence=0.96,
        metadata=scope,
    )

    packet = build_working_memory_packet(
        store,
        query="Magyarázd el ezt a kódot röviden.",
        session_id="session-style-ordinary",
        principal_scope_key=principal_scope_key,
        profile_match_limit=6,
        continuity_recent_limit=2,
        continuity_match_limit=2,
        transcript_match_limit=2,
        transcript_char_budget=500,
        graph_limit=2,
        corpus_limit=2,
        corpus_char_budget=500,
        route_resolver=lambda query: (_ for _ in ()).throw(RuntimeError("forced fallback")),
    )

    assert packet["routing"]["applied_mode"] == "fact"
    assert packet["routing"]["source"] == "route_resolution_failed"
    assert packet["routing"]["resolution_status"] == "failed"
    assert packet["routing"]["resolution_error"] == "forced fallback"
    assert packet["routing"]["reason"] == "route resolver failed; staying on fact route"
    assert all(row["stable_key"] != STYLE_CONTRACT_SLOT for row in packet["profile_items"])
    assert STYLE_CONTRACT_SLOT not in packet["block"]


def test_open_backfills_compiled_behavior_policy_from_existing_style_contract_row(tmp_path):
    db_path = tmp_path / "brainstack.db"
    store = BrainstackStore(str(db_path))
    store.open()
    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])
    store.upsert_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        category="preference",
        content=(
            "User style contract\n\n"
            "Kommunikációs minták:\n"
            "- Chatbot maradványok tilos\n"
            "- Knowledge cutoff disclaimer tilos"
        ),
        source="test",
        confidence=0.96,
        metadata=scope,
    )
    store.conn.execute("DELETE FROM compiled_behavior_policies")
    store.conn.execute(
        "DELETE FROM applied_migrations WHERE name = ?",
        ("compiled_behavior_policy_v1",),
    )
    store.conn.execute(
        "DELETE FROM applied_migrations WHERE name = ?",
        (MIGRATION_COMPILED_BEHAVIOR_POLICY_V2,),
    )
    store.conn.commit()
    store.close()

    reopened = BrainstackStore(str(db_path))
    reopened.open()
    try:
        compiled = reopened.get_compiled_behavior_policy(principal_scope_key=principal_scope_key)
        assert compiled is not None
        assert compiled["policy"]["compiler_version"] == BEHAVIOR_POLICY_COMPILER_VERSION
        assert compiled["policy"]["source_storage_key"].startswith("behavior_contract::")
        assert compiled["policy"]["no_silent_drop"] is True
        assert len(compiled["policy"]["coverage"]) == compiled["policy"]["raw_rule_count"]
        assert "Chatbot maradványok tilos" in compiled["projection_text"]
    finally:
        reopened.close()


def test_style_contract_explicit_recall_stays_bounded_for_oversized_contracts(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])

    oversized_contract = "User style contract\n\n" + "\n".join(
        f"- Rule {index}: keep the wording precise and concrete."
        for index in range(1, 220)
    )
    assert len(oversized_contract) > 2400

    store.upsert_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        category="preference",
        content=oversized_contract,
        source="test",
        confidence=0.96,
        metadata=scope,
    )

    explicit_packet = build_working_memory_packet(
        store,
        query="Do you know the 29 style rules?",
        session_id="session-style-bounded",
        principal_scope_key=principal_scope_key,
        profile_match_limit=6,
        continuity_recent_limit=2,
        continuity_match_limit=2,
        transcript_match_limit=2,
        transcript_char_budget=500,
        graph_limit=2,
        corpus_limit=2,
        corpus_char_budget=500,
        route_resolver=lambda query: {"mode": "style_contract", "reason": "test"},
    )

    profile_section = explicit_packet["block"].split("## Brainstack Canonical Behavior Contract\n", 1)[1]
    assert "User style contract" in profile_section
    assert "- Rule 1: keep the wording precise and concrete." in profile_section
    assert "..." in profile_section


def test_open_migrates_legacy_style_contract_corpus_document_into_profile_lane_and_retires_document(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])

    store.ingest_corpus_document(
        stable_key="legacy-style-contract",
        title="User style contract",
        doc_kind=STYLE_CONTRACT_DOC_KIND,
        source="test",
        metadata=scope,
        sections=[
            {
                "heading": "Tartalmi minták",
                "content": "Konkrét tények, nem jelentőségfelfújás\nEgy konkrét forrás, nem homályos hivatkozások",
                "section_index": 0,
            }
        ],
    )
    store.conn.execute(
        "DELETE FROM applied_migrations WHERE name = ?",
        ("style_contract_profile_lane_v1",),
    )
    store.conn.commit()
    store.close()

    reopened = BrainstackStore(str(tmp_path / "brainstack.db"))
    reopened.open()
    try:
        row = reopened.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=principal_scope_key,
        )
        assert row is not None
        assert "User style contract" in row["content"]
        assert "Tartalmi minták:" in row["content"]

        active_docs = reopened.conn.execute(
            "SELECT COUNT(*) FROM corpus_documents WHERE doc_kind = ? AND active = 1",
            (STYLE_CONTRACT_DOC_KIND,),
        ).fetchone()[0]
        assert active_docs == 0

        marker = reopened.conn.execute(
            "SELECT 1 FROM applied_migrations WHERE name = 'style_contract_profile_lane_v1'"
        ).fetchone()
        assert marker is not None
    finally:
        reopened.close()
