# ruff: noqa: E402
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location("phase21_host_import_shims", _host_shims_path)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack.db import BrainstackStore
from brainstack import BrainstackMemoryProvider
from brainstack.reconciler import reconcile_tier2_candidates
from brainstack.retrieval import build_system_prompt_block
from brainstack.tier2_extractor import _default_llm_caller, extract_tier2_candidates


def test_reconcile_preserves_prefixed_profile_slots_without_double_prefix(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()

    reconcile_tier2_candidates(
        store,
        session_id="session-21-slot",
        turn_number=1,
        source="tier2:test",
        extracted={
            "profile_items": [
                {
                    "category": "preference",
                    "slot": "preference:communication_style",
                    "content": "Use Humanizer style by default.",
                    "confidence": 0.92,
                }
            ]
        },
    )

    stable_keys = {row["stable_key"] for row in store.list_profile_items(limit=10)}
    assert "preference:communication_style" in stable_keys
    assert "preference:preference:communication_style" not in stable_keys


def test_reconcile_uses_identity_user_name_for_user_alias_canonicalization(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    store.upsert_profile_item(
        stable_key="identity:user_name",
        category="identity",
        content="User's name is Tomi (Discord: LauraTom).",
        source="test",
        confidence=0.97,
    )

    reconcile_tier2_candidates(
        store,
        session_id="session-21-user-name",
        turn_number=2,
        source="tier2:test",
        extracted={
            "states": [
                {
                    "subject": "User",
                    "attribute": "preferred_pet_name",
                    "value": "Laura",
                    "supersede": False,
                    "confidence": 0.85,
                }
            ]
        },
    )

    rows = store.search_graph(query="Tomi preferred_pet_name Laura", limit=10)
    assert any(row["subject"] == "Tomi" and row["predicate"] == "preferred_pet_name" for row in rows)


def test_tier2_extractor_drops_internal_persona_and_skill_mechanics_but_keeps_real_preferences():
    def _fake_llm_caller(**kwargs):
        return {
            "content": json.dumps(
                {
                    "profile_items": [
                        {
                            "category": "preference",
                            "slot": "humanizer",
                            "content": "Use Humanizer style by default.",
                            "confidence": 0.9,
                        },
                        {
                            "category": "shared_work",
                            "content": "Maintains persona.md and Humanizer SKILL.md for style consistency.",
                            "confidence": 0.8,
                        },
                    ],
                    "states": [
                        {
                            "subject": "Assistant",
                            "attribute": "communication_style",
                            "value": "Humanizer (SKILL.md)",
                            "supersede": True,
                            "confidence": 0.78,
                        },
                        {
                            "subject": "Assistant",
                            "attribute": "message_structure",
                            "value": "Use new lines for distinct thoughts.",
                            "supersede": True,
                            "confidence": 0.82,
                        },
                    ],
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
        [
            {"turn_number": 1, "kind": "turn", "content": "Tomi vagyok.", "created_at": "2026-04-16T00:00:00Z"},
            {
                "turn_number": 2,
                "kind": "turn",
                "content": "A Humanizer stílus legyen az alap. Új gondolat új sorba kerüljön.",
                "created_at": "2026-04-16T00:01:00Z",
            },
        ],
        llm_caller=_fake_llm_caller,
    )

    assert extracted["profile_items"] == [
        {
            "category": "preference",
            "content": "Use humanizer style.",
            "confidence": 0.9,
            "source": "tier2_llm",
            "slot": "preference:communication_style",
        },
        {
            "category": "preference",
            "content": "Put each new thought on a new line.",
            "confidence": 0.86,
            "source": "tier2_transcript_rule",
            "slot": "preference:message_structure",
        },
    ]
    assert extracted["states"] == [
        {
            "subject": "Assistant",
            "attribute": "message_structure",
            "value": "Use new lines for distinct thoughts.",
            "supersede": True,
            "confidence": 0.82,
        }
    ]


def test_tier2_extractor_recovers_last_json_object_after_reasoning_preamble():
    def _fake_llm_caller(**kwargs):
        return {
            "content": (
                "First, I should restate the schema.\n"
                "Schema example: {\"profile_items\": [], \"states\": []}\n"
                "Now the actual answer follows.\n"
                "{\"profile_items\": [{\"category\": \"preference\", \"slot\": \"response_language\", "
                "\"content\": \"Always respond in Hungarian.\", \"confidence\": 0.93}], "
                "\"states\": [], \"relations\": [], \"inferred_relations\": [], "
                "\"typed_entities\": [], \"temporal_events\": [], "
                "\"continuity_summary\": \"\", \"decisions\": []}"
            )
        }

    extracted = extract_tier2_candidates(
        [
            {
                "turn_number": 1,
                "kind": "turn",
                "content": "Mindig magyarul válaszolj.",
                "created_at": "2026-04-16T00:00:00Z",
            }
        ],
        llm_caller=_fake_llm_caller,
    )

    assert extracted["_meta"]["json_parse_status"] == "json_embedded"
    assert extracted["profile_items"] == [
        {
            "category": "preference",
            "content": "Always respond in Hungarian.",
            "confidence": 0.93,
            "source": "tier2_llm",
            "slot": "preference:response_language",
        }
    ]


def test_tier2_default_llm_caller_requests_json_object(monkeypatch):
    import sys
    import types

    captured: dict[str, object] = {}

    def _fake_call_llm(*, task, messages, temperature, max_tokens, timeout, extra_body=None):
        captured.update(
            {
                "task": task,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": timeout,
                "extra_body": extra_body,
            }
        )
        return {"content": "{\"profile_items\": [], \"states\": []}"}

    fake_module = types.ModuleType("agent.auxiliary_client")
    fake_module.call_llm = _fake_call_llm
    monkeypatch.setitem(sys.modules, "agent.auxiliary_client", fake_module)

    _default_llm_caller(
        task="flush_memories",
        messages=[{"role": "user", "content": "test"}],
        timeout=12.0,
        max_tokens=256,
    )

    assert captured["task"] == "flush_memories"
    assert captured["extra_body"] == {"response_format": {"type": "json_object"}}


def test_tier2_prompt_requests_separate_communication_profile_slots():
    captured: dict[str, object] = {}

    def _fake_llm_caller(**kwargs):
        captured.update(kwargs)
        return {"content": "{\"profile_items\": [], \"states\": [], \"relations\": [], \"inferred_relations\": [], \"typed_entities\": [], \"temporal_events\": [], \"continuity_summary\": \"\", \"decisions\": []}"}

    extract_tier2_candidates(
        [
            {
                "turn_number": 1,
                "kind": "turn",
                "content": "A Te neved Bestie. Mindig magyarul válaszolj. Ne használj emojikat.",
                "created_at": "2026-04-16T00:00:00Z",
            }
        ],
        llm_caller=_fake_llm_caller,
    )

    system_prompt = str(captured["messages"][0]["content"])
    assert "emit them as separate durable profile_items" in system_prompt
    assert "preference:response_language, preference:ai_name" in system_prompt
    assert "preference:pronoun_capitalization" in system_prompt
    assert "preference:dash_usage" in system_prompt


def test_tier2_extractor_splits_bundled_communication_rules_into_canonical_slots():
    def _fake_llm_caller(**kwargs):
        return {
            "content": json.dumps(
                {
                    "profile_items": [
                        {
                            "category": "preference",
                            "slot": "communication_style",
                            "content": (
                                "Use Humanizer style, always answer in Hungarian, call yourself Bestie, "
                                "do not use emojis, put new thoughts on new lines, capitalize Én/Te/Ő, "
                                "and do not use dash punctuation."
                            ),
                            "confidence": 0.98,
                        }
                    ],
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
        [
            {
                "turn_number": 1,
                "kind": "turn",
                "content": "A Te neved Bestie. Mindig magyarul válaszolj. Ne használj emojikat.",
                "created_at": "2026-04-16T00:00:00Z",
            }
        ],
        llm_caller=_fake_llm_caller,
    )

    slots = {item["slot"] for item in extracted["profile_items"]}
    assert "preference:response_language" in slots
    assert "preference:ai_name" in slots
    assert "preference:communication_style" in slots
    assert "preference:emoji_usage" in slots
    assert "preference:message_structure" in slots
    assert "preference:pronoun_capitalization" in slots
    assert "preference:dash_usage" in slots


def test_tier2_extractor_derives_missing_pronoun_and_dash_rules_from_transcript():
    def _fake_llm_caller(**kwargs):
        return {
            "content": json.dumps(
                {
                    "profile_items": [
                        {
                            "category": "preference",
                            "slot": "communication_style",
                            "content": "Use Humanizer style, always answer in Hungarian, call yourself Bestie, do not use emojis, and put new thoughts on new lines.",
                            "confidence": 0.98,
                        }
                    ],
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
        [
            {
                "turn_number": 1,
                "kind": "turn",
                "content": "Az Én, Te és Ő szavakat nagybetűvel írd. Ne használj dash jeleket.",
                "created_at": "2026-04-16T00:00:00Z",
            }
        ],
        llm_caller=_fake_llm_caller,
    )

    slots = {item["slot"] for item in extracted["profile_items"]}
    assert "preference:pronoun_capitalization" in slots
    assert "preference:dash_usage" in slots


def test_system_prompt_contract_promotes_broader_behavior_rules_and_filters_internal_noise(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    store.upsert_profile_item(
        stable_key="preference:communication_style",
        category="preference",
        content="Use Humanizer style: direct, concrete, no emoji.",
        source="test",
        confidence=0.94,
    )
    store.upsert_profile_item(
        stable_key="preference:response_language",
        category="preference",
        content="Always respond in Hungarian.",
        source="test",
        confidence=0.93,
    )
    store.upsert_profile_item(
        stable_key="preference:message_structure",
        category="preference",
        content="Use new lines for distinct thoughts.",
        source="test",
        confidence=0.92,
    )
    store.upsert_profile_item(
        stable_key="preference:formatting_style",
        category="preference",
        content="Capitalize Én, Te, and Ő.",
        source="test",
        confidence=0.92,
    )
    store.upsert_profile_item(
        stable_key="preference:dash_usage",
        category="preference",
        content="Do not use dash punctuation in replies.",
        source="test",
        confidence=0.92,
    )
    store.upsert_profile_item(
        stable_key="preference:ai_name",
        category="preference",
        content="The user calls the AI Bestie.",
        source="test",
        confidence=0.92,
    )
    store.upsert_graph_state(
        subject_name="Assistant",
        attribute="message_structure",
        value_text="Keep readable paragraph breaks.",
        source="test",
        supersede=True,
    )
    store.upsert_graph_state(
        subject_name="Assistant",
        attribute="communication_style",
        value_text="Humanizer (SKILL.md)",
        source="test",
        supersede=True,
    )
    store.upsert_graph_state(
        subject_name="Assistant",
        attribute="response_style",
        value_text="Use Humanizer style, new lines, and capitalize Én, Te, Ő.",
        source="test",
        supersede=True,
    )
    store.upsert_graph_state(
        subject_name="User",
        attribute="communication_style",
        value_text="Humanizer style, no emojis, new line for new thought, capitalize Én, Te, Ő.",
        source="test",
        supersede=True,
    )
    store.upsert_graph_state(
        subject_name="Assistant",
        attribute="name",
        value_text="Bestie",
        source="test",
        supersede=True,
    )

    block = build_system_prompt_block(store, profile_limit=10)

    assert "# Brainstack Active Communication Contract" in block
    assert "Use Humanizer style: direct, concrete, natural, and low-fluff." in block
    assert "Always respond in Hungarian." in block
    assert "Put each new thought on its own line." in block
    assert "Capitalize Én, Te, and Ő when you use them." in block
    assert "Do not use dash punctuation in replies." in block
    assert "Keep readable paragraph breaks." not in block
    assert "Humanizer style, no emojis, new line for new thought, capitalize Én, Te, Ő." not in block
    assert "Use Humanizer style, new lines, and capitalize Én, Te, Ő." in block
    assert "Refer to yourself as Bestie when naming yourself." in block
    assert "SKILL.md" not in block
    assert "[preference] Always respond in Hungarian." not in block


def test_phase21_end_to_end_prefetch_uses_clean_contract_without_side_memory_noise(tmp_path):
    base = Path(tmp_path)

    def _fake_llm_caller(**kwargs):
        return {
            "content": json.dumps(
                {
                    "profile_items": [
                        {
                            "category": "identity",
                            "slot": "identity:user_name",
                            "content": "User's name is Tomi (Discord: LauraTom).",
                            "confidence": 0.97,
                        },
                        {
                            "category": "preference",
                            "slot": "communication_style",
                            "content": "Use Humanizer style: direct, concrete, no emoji.",
                            "confidence": 0.94,
                        },
                        {
                            "category": "preference",
                            "slot": "preference:response_language",
                            "content": "Always respond in Hungarian.",
                            "confidence": 0.94,
                        },
                        {
                            "category": "preference",
                            "slot": "preference:ai_name",
                            "content": "The user calls the AI Bestie.",
                            "confidence": 0.93,
                        },
                        {
                            "category": "preference",
                            "slot": "message_structure",
                            "content": "Use new lines for distinct thoughts.",
                            "confidence": 0.92,
                        },
                        {
                            "category": "preference",
                            "slot": "formatting_style",
                            "content": "Capitalize Én, Te, and Ő.",
                            "confidence": 0.92,
                        },
                        {
                            "category": "preference",
                            "slot": "dash_usage",
                            "content": "Do not use dash punctuation in replies.",
                            "confidence": 0.92,
                        },
                        {
                            "category": "shared_work",
                            "content": "Maintains persona.md and Humanizer SKILL.md for style consistency.",
                            "confidence": 0.8,
                        },
                    ],
                    "states": [
                        {
                            "subject": "Assistant",
                            "attribute": "communication_style",
                            "value": "Use Humanizer style: direct, concrete, no emoji.",
                            "supersede": True,
                            "confidence": 0.91,
                        },
                        {
                            "subject": "Assistant",
                            "attribute": "message_structure",
                            "value": "Keep readable paragraph breaks.",
                            "supersede": True,
                            "confidence": 0.83,
                        },
                        {
                            "subject": "Assistant",
                            "attribute": "communication_style",
                            "value": "Humanizer (SKILL.md)",
                            "supersede": True,
                            "confidence": 0.7,
                        },
                        {
                            "subject": "Assistant",
                            "attribute": "memory_method",
                            "value": "passive Brainstack only; no manual tool/code usage",
                            "supersede": True,
                            "confidence": 0.7,
                        },
                    ],
                    "relations": [],
                    "inferred_relations": [],
                    "typed_entities": [],
                    "temporal_events": [],
                    "continuity_summary": "Tomi prefers Hungarian Humanizer-style replies and calls the AI Bestie.",
                    "decisions": ["Do not use memory side-files or ad hoc code for personal memory."],
                }
            )
        }

    def _fake_extractor(rows, **kwargs):
        return extract_tier2_candidates(rows, llm_caller=_fake_llm_caller)

    provider = BrainstackMemoryProvider(
        config={
            "db_path": str(base / "brainstack.db"),
            "tier2_batch_turn_limit": 1,
            "_tier2_extractor": _fake_extractor,
        }
    )
    provider.initialize("session-phase21-a", hermes_home=str(base), user_id="user-1", platform="discord")

    try:
        provider.sync_turn(
            "A nevem Tomi. Magyarul válaszolj. Hívj Bestie-nek. Új gondolat új sorba kerüljön.",
            "Megvan.",
            session_id="session-phase21-a",
        )
        assert provider._wait_for_tier2_worker(timeout=1.0) is True

        provider.initialize("session-phase21-b", hermes_home=str(base), user_id="user-1", platform="discord")
        prompt_block = build_system_prompt_block(
            provider._store,
            profile_limit=10,
            principal_scope_key=provider._principal_scope_key,
        )
        block = provider.prefetch("Tudod hogy hívnak engem?", session_id="session-phase21-b")

        assert "# Brainstack Active Communication Contract" in prompt_block
        assert "Always respond in Hungarian." in prompt_block
        assert "Refer to yourself as Bestie when naming yourself." in prompt_block
        assert "Put each new thought on its own line." in prompt_block
        assert "Capitalize Én, Te, and Ő when you use them." in prompt_block
        assert "Do not use dash punctuation in replies." in prompt_block
        assert "Use Humanizer style: direct, concrete, natural, and low-fluff." in prompt_block
        assert "persona.md" not in prompt_block
        assert "SKILL.md" not in prompt_block
        assert "persona.md" not in block
        assert "SKILL.md" not in block

        profile_rows = provider._store.list_profile_items(limit=20)
        graph_rows = provider._store.search_graph(query="Assistant Tomi Bestie", limit=20)

        assert not any("persona.md" in row["content"].lower() for row in profile_rows)
        assert not any("skill.md" in str(row.get("object_value") or "").lower() for row in graph_rows)
        assert any(row["stable_key"] == "preference:response_language" for row in profile_rows)
        assert any(row["stable_key"] == "preference:ai_name" for row in profile_rows)
    finally:
        provider.shutdown()
