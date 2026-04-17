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
from brainstack.db import BrainstackStore
from brainstack.reconciler import reconcile_tier2_candidates
from brainstack.retrieval import build_system_prompt_block
from brainstack.style_contract import STYLE_CONTRACT_DOC_KIND, STYLE_CONTRACT_SLOT
from brainstack.tier2_extractor import extract_tier2_candidates


def _scope(platform: str, user_id: str) -> dict[str, object]:
    principal_scope = {
        "platform": platform,
        "user_id": user_id,
        "agent_identity": "bestie",
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
                        "title": "Humanizer style contract",
                        "summary": "Use the full Humanizer rules on demand.",
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
        [{"turn_number": 1, "kind": "turn", "content": "User pasted the full Humanizer rule pack."}],
        llm_caller=_fake_llm_caller,
    )

    assert extracted["style_contract"] is not None
    assert extracted["style_contract"]["slot"] == STYLE_CONTRACT_SLOT
    assert "Humanizer style contract" in extracted["style_contract"]["content"]
    assert "Tartalmi minták:" in extracted["style_contract"]["content"]
    assert "- Konkrét tények, nem jelentőségfelfújás" in extracted["style_contract"]["content"]


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
                "title": "Humanizer style contract",
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
            "Humanizer style contract\n\n"
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
        query="Do you know the 29 Humanizer rules?",
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
    assert "Humanizer style contract" in explicit_packet["block"]

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

    assert all(row["stable_key"] != STYLE_CONTRACT_SLOT for row in ordinary_packet["profile_items"])
    assert "Humanizer style contract" not in ordinary_packet["block"]

    system_prompt = build_system_prompt_block(
        store,
        profile_limit=10,
        principal_scope_key=principal_scope_key,
    )
    assert "Always respond in Hungarian." in system_prompt
    assert "Humanizer style contract" not in system_prompt


def test_open_migrates_legacy_style_contract_corpus_document_into_profile_lane_and_retires_document(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])

    store.ingest_corpus_document(
        stable_key="legacy-style-contract",
        title="Humanizer style contract",
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
        assert "Humanizer style contract" in row["content"]
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
