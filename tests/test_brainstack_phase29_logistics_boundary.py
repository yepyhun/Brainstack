# ruff: noqa: E402
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location("phase29_host_import_shims", _host_shims_path)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack.db import BrainstackStore
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


def test_tier2_extractor_derives_stable_provider_location_typed_entity_when_llm_omits_it():
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
        [
            {
                "turn_number": 1,
                "kind": "turn",
                "content": (
                    "User: [LauraTom] Kassák Lajos 87 44es kapucsengő 4em Jegyezd meg ez a talpmasszázs címe (Móni). "
                    "Assistant: Megjegyeztem, Tomi."
                ),
                "created_at": "2026-04-17T08:30:00Z",
            }
        ],
        llm_caller=_fake_llm_caller,
    )

    assert extracted["typed_entities"] == [
        {
            "turn_number": 1,
            "name": "Móni",
            "entity_type": "service_provider",
            "subject": "User",
            "attributes": {
                "address": "Kassák Lajos 87 44es kapucsengő 4em",
                "category": "talpmasszázs",
            },
            "confidence": 0.86,
            "metadata": {"event_turn_number": 1, "source": "tier2_transcript_rule"},
            "temporal": {"observed_at": "2026-04-17T08:30:00Z"},
        }
    ]


def test_tier2_extractor_does_not_promote_same_day_todos_to_durable_logistics_entities():
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
        [
            {
                "turn_number": 1,
                "kind": "turn",
                "content": "Fodrász bank ma elintézni.",
                "created_at": "2026-04-17T09:00:00Z",
            }
        ],
        llm_caller=_fake_llm_caller,
    )

    assert extracted["typed_entities"] == []


def test_open_backfills_stable_provider_location_into_principal_scoped_graph(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()

    scope_a = _scope("discord", "user-a")
    principal_scope_key = str(scope_a["principal_scope_key"])

    store.add_transcript_entry(
        session_id="session-logistics-a",
        turn_number=1,
        kind="turn",
        content=(
            "User: [LauraTom] Kassák Lajos 87 44es kapucsengő 4em Jegyezd meg ez a talpmasszázs címe (Móni). "
            "Assistant: Megjegyeztem, Tomi."
        ),
        source="sync_turn",
        metadata=scope_a,
    )
    store.conn.execute(
        "DELETE FROM applied_migrations WHERE name IN (?, ?)",
        ("stable_logistics_typed_entities_v1", "stable_logistics_typed_entities_v2"),
    )
    store.conn.commit()
    store.close()

    reopened = BrainstackStore(str(tmp_path / "brainstack.db"))
    reopened.open()
    try:
        rows = reopened.search_graph(
            query="Móni Kassák talpmasszázs",
            limit=20,
            principal_scope_key=principal_scope_key,
        )

        assert any(
            row["row_type"] == "state"
            and row["subject"] == "Móni"
            and row["predicate"] == "address"
            and "Kassák Lajos 87" in row["object_value"]
            for row in rows
        )
        assert any(
            row["row_type"] == "state"
            and row["subject"] == "Móni"
            and row["predicate"] == "category"
            and row["object_value"] == "talpmasszázs"
            for row in rows
        )
        marker = reopened.conn.execute(
            "SELECT 1 FROM applied_migrations WHERE name = 'stable_logistics_typed_entities_v2'"
        ).fetchone()
        assert marker is not None
    finally:
        reopened.close()
