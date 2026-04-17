# ruff: noqa: E402
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location("phase293_host_import_shims", _host_shims_path)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack.control_plane import analyze_query, build_working_memory_packet
from brainstack.db import BrainstackStore
from brainstack.reconciler import reconcile_tier2_candidates
from brainstack.style_contract import build_style_contract_stable_key, derive_transcript_style_contract_artifact
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


def _humanizer_rows() -> list[dict[str, object]]:
    return [
        {
            "turn_number": 1,
            "kind": "turn",
            "content": (
                "Tartalmi minták (1-5):\n"
                "Konkrét tények, nem jelentőségfelfújás\n"
                "Egy konkrét forrás, nem homályos hivatkozások\n"
                "Kerüljük az -ing elemzéseket\n"
                "Homályos hivatkozások helyett konkrét forrás\n"
                "Sablonos \"Kihívások\" szakasz kerülendő\n\n"
                "Nyelvi minták (6-18):\n"
                "Is/are a \"serves as\" helyett\n"
                "Nincs negatív párhuzam\n"
                "Nincs hármas szabály\n"
                "Nincs szinonímacsere\n"
                "Nincs hamis skála"
            ),
            "created_at": "2026-04-17T15:40:00Z",
        },
        {
            "turn_number": 2,
            "kind": "turn",
            "content": (
                "Kommunikációs minták (18-20):\n"
                "Chatbot maradványok tilos\n"
                "Knowledge-cutoff disclaimer tilos\n"
                "Szervilis hangnem tilos\n\n"
                "Töltelék (21-24):\n"
                "Töltelékszövegek röviden\n"
                "Nincs túlzott óvatoskodás\n"
                "Nincs generikus pozitív zárás\n"
                "Kötőjeles szópárok mértékkel\n\n"
                "Stílus minták (25-29):\n"
                "Meggyőző autoritás klisék kerülendő\n"
                "\"Let's dive in\" jellegű bejelentések tilos\n"
                "Töredékes fejlécek kerülendő"
            ),
            "created_at": "2026-04-17T15:41:00Z",
        },
    ]


def test_tier2_extractor_derives_style_contract_artifact_from_structured_humanizer_rows():
    def _fake_llm_caller(**kwargs):
        return {
            "content": json.dumps(
                {
                    "profile_items": [],
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
        _humanizer_rows(),
        llm_caller=_fake_llm_caller,
    )

    artifact = extracted["style_contract_artifact"]
    assert artifact is not None
    assert artifact["doc_kind"] == "style_contract"
    assert "Tartalmi minták" in artifact["content"]
    assert "Stílus minták" in artifact["content"]


def test_style_contract_artifact_derives_from_flattened_transcript_entry():
    flattened = (
        'User: [LauraTom] Tartalmi minták (1-5): Konkrét tények, nem jelentőségfelfújás '
        'Egy konkrét forrás, nem homályos hivatkozások Kerüljük az -ing elemzéseket '
        'Homályos hivatkozások helyett konkrét forrás Sablonos "Kihívások" szakasz kerülendő '
        'Nyelvi minták (6-18): Is/are a "serves as" helyett Nincs negatív párhuzam '
        'Nincs hármas szabály Nincs szinonímacsere Nincs hamis skála '
        'Kommunikációs minták (18-20): Chatbot maradványok tilos Knowledge-cutoff disclaimer tilos '
        'Szervilis hangnem tilos Töltelék (21-24): Töltelékszövegek röviden Nincs túlzott óvatoskodás '
        'Nincs generikus pozitív zárás Kötőjeles szópárok mértékkel '
        "Stílus minták (25-29): Meggyőző autoritás klisék kerülendő \"Let's dive in\" jellegű bejelentések tilos "
        'Töredékes fejlécek kerülendő\\nAssistant: Köszi, megjegyzem.'
    )

    artifact = derive_transcript_style_contract_artifact(
        [{"content": flattened}],
        source="tier2:test",
    )

    assert artifact is not None
    assert "Tartalmi minták:" in artifact["content"]
    assert "Nyelvi minták:" in artifact["content"]
    assert "Stílus minták:" in artifact["content"]
    assert artifact["content"].startswith("Tartalmi minták:")


def test_working_memory_packet_prefers_exact_style_contract_artifact_for_direct_rule_query(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()

    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])

    reconcile_tier2_candidates(
        store,
        session_id="session-style",
        turn_number=2,
        source="tier2:test",
        metadata=scope,
        extracted={
            "profile_items": [
                {
                    "category": "preference",
                    "slot": "preference:communication_style",
                    "content": "Use humanizer style.",
                    "confidence": 0.9,
                }
            ],
            "states": [],
            "relations": [],
            "inferred_relations": [],
            "style_contract_artifact": {
                "title": "Humanizer style contract",
                "doc_kind": "style_contract",
                "content": "\n\n".join(row["content"] for row in _humanizer_rows()),
                "source": "tier2:test",
                "confidence": 0.9,
            },
            "typed_entities": [],
            "temporal_events": [],
            "continuity_summary": "",
            "decisions": [],
        },
    )

    packet = build_working_memory_packet(
        store,
        query="Tudod mind a 29 szabályt?",
        session_id="session-style",
        principal_scope_key=principal_scope_key,
        profile_match_limit=4,
        continuity_recent_limit=2,
        continuity_match_limit=2,
        transcript_match_limit=2,
        transcript_char_budget=640,
        graph_limit=2,
        corpus_limit=2,
        corpus_char_budget=2400,
    )

    assert packet["analysis"]["style_contract_targets"] == ("humanizer",)
    assert packet["corpus_rows"]
    assert packet["corpus_rows"][0]["doc_kind"] == "style_contract"
    assert packet["corpus_rows"][0]["match_mode"] == "direct"
    assert "Tartalmi minták" in packet["corpus_rows"][0]["content"]
    assert packet["policy"]["confidence_band"] == "high"

    ordinary_packet = build_working_memory_packet(
        store,
        query="Beszélgessünk egy kicsit!",
        session_id="session-style",
        principal_scope_key=principal_scope_key,
        profile_match_limit=4,
        continuity_recent_limit=2,
        continuity_match_limit=2,
        transcript_match_limit=2,
        transcript_char_budget=640,
        graph_limit=2,
        corpus_limit=2,
        corpus_char_budget=2400,
    )
    assert ordinary_packet["corpus_rows"] == []


def test_open_runs_style_contract_hygiene_and_backfill_migrations(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()

    scope = _scope("discord", "user-a")
    principal_scope_key = str(scope["principal_scope_key"])

    store.upsert_profile_item(
        stable_key="preference:style_preference",
        category="preference",
        content="Humanizer style: natural, direct, no emojis/bolding, varied sentence length.",
        source="test",
        confidence=0.84,
        metadata=scope,
    )
    store.upsert_profile_item(
        stable_key="shared_work:shared_work:config",
        category="shared_work",
        content="Maintains persona.md and Humanizer SKILL.md for style consistency.",
        source="test",
        confidence=0.7,
        metadata=scope,
    )
    for row in _humanizer_rows():
        store.add_transcript_entry(
            session_id="session-style",
            turn_number=int(row["turn_number"]),
            kind=str(row["kind"]),
            content=str(row["content"]),
            source="sync_turn",
            metadata=scope,
            created_at=str(row["created_at"]),
        )
    store.conn.execute(
        "DELETE FROM applied_migrations WHERE name IN (?, ?, ?, ?)",
        (
            "style_contract_hygiene_v1",
            "style_contract_artifact_backfill_v1",
            "style_contract_artifact_backfill_v2",
            "style_contract_artifact_backfill_v3",
        ),
    )
    store.conn.commit()
    store.close()

    reopened = BrainstackStore(str(tmp_path / "brainstack.db"))
    reopened.open()
    try:
        profile_rows = reopened.list_profile_items(limit=50, principal_scope_key=principal_scope_key)
        stable_keys = {row["stable_key"] for row in profile_rows}
        assert "preference:communication_style" in stable_keys
        assert "preference:style_preference" not in stable_keys
        assert not any("persona.md" in row["content"].lower() for row in profile_rows)
        assert not any("skill.md" in row["content"].lower() for row in profile_rows)

        snapshot = reopened.get_corpus_document(
            stable_key=build_style_contract_stable_key(principal_scope_key=principal_scope_key)
        )
        assert snapshot is not None
        combined = "\n\n".join(
            str(section.get("content") or "").strip()
            for section in list(snapshot.get("sections") or [])
            if str(section.get("content") or "").strip()
        )
        assert "Tartalmi minták" in combined
        assert "Stílus minták" in combined

        migration_rows = {
            row[0]
            for row in reopened.conn.execute(
                "SELECT name FROM applied_migrations WHERE name IN (?, ?)",
                ("style_contract_hygiene_v1", "style_contract_artifact_backfill_v3"),
            ).fetchall()
        }
        assert migration_rows == {"style_contract_hygiene_v1", "style_contract_artifact_backfill_v3"}
    finally:
        reopened.close()


def test_analyze_query_only_targets_style_contract_for_explicit_rule_queries():
    assert analyze_query("Tudod mind a 29 szabályt?").style_contract_targets == ("humanizer",)
    assert analyze_query("A humanizerről és ezen szabályokról mit tudsz?").style_contract_targets == ("humanizer",)
    assert analyze_query("Mi a mai napi teendőm?").style_contract_targets == ()
