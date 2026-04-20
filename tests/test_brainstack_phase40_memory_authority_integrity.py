from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location(
    "phase40_host_import_shims",
    _host_shims_path,
)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider  # noqa: E402
from brainstack.db import (  # noqa: E402
    BEHAVIOR_CONTRACT_ACTIVE_STATUS,
    BEHAVIOR_CONTRACT_SUPERSEDED_STATUS,
    STYLE_CONTRACT_SLOT,
)
from brainstack.tier2_extractor import extract_tier2_candidates  # noqa: E402


def _make_provider(tmp_path: Path, session_id: str) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(config={"db_path": str(tmp_path / "brainstack.db")})
    provider.initialize(
        session_id,
        hermes_home=str(tmp_path),
        user_id="user-1",
        platform="discord",
        agent_identity="assistant-main",
        agent_workspace="workspace-a",
    )
    return provider


def _style_contract_text() -> str:
    return (
        "A set of 25 rules for communication style and formatting.\n\n"
        "Rules:\n"
        "- Bestie-kent hivatkozom magamra amikor nevet adok magamnak.\n"
        "- Nem hasznalok emojikat.\n"
        "- Nem hasznalok kotohjeles irasjeleket a valaszokban.\n"
        "- En, Te, O nagybetuvel irando.\n"
        "- Kozvetlen, konkret, termeszetes es alacsony felesleges szoveges stilust hasznalok.\n"
        "- Gondolatonkent uj sort kezdek.\n"
    )


def _task_capture_text() -> str:
    return (
        "Tasks for today:\n"
        "- review the phase 40 authority plan\n"
        "- write the phase 40 verification summary\n"
    )


def _operating_truth_text() -> str:
    return (
        "Active work:\n"
        "- Phase 40 authority convergence\n\n"
        "Current commitments:\n"
        "- Keep reads side-effect free\n\n"
        "Next steps:\n"
        "- Repair the dirty store\n"
    )


def test_prefetch_is_read_only_even_when_candidates_are_detected(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase40-prefetch-read-only")
    try:
        provider.prefetch(_style_contract_text(), session_id="phase40-prefetch-read-only")
        provider.prefetch(_task_capture_text(), session_id="phase40-prefetch-read-only")
        provider.prefetch(_operating_truth_text(), session_id="phase40-prefetch-read-only")

        store = provider._store
        assert store is not None
        assert store.get_behavior_contract(principal_scope_key=provider._principal_scope_key) is None
        assert store.list_task_items(principal_scope_key=provider._principal_scope_key, limit=10) == []
        assert store.list_operating_records(principal_scope_key=provider._principal_scope_key, limit=10) == []

        debug = provider.memory_authority_debug()
        assert debug is not None
        assert debug["read_side_effect_count"] == 0
        assert debug["write_receipts_in_packet"] is False
        assert debug["candidate_writes"]["operating_truth"] is True
    finally:
        provider.shutdown()


def test_sync_turn_is_the_explicit_write_path_for_task_and_style_truth(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase40-sync-turn-write")
    try:
        provider.sync_turn(_style_contract_text(), "ertettem", session_id="phase40-sync-turn-write")
        provider.sync_turn(_task_capture_text(), "ertettem", session_id="phase40-sync-turn-write")
        provider.sync_turn(_operating_truth_text(), "ertettem", session_id="phase40-sync-turn-write")

        store = provider._store
        assert store is not None
        contract = store.get_behavior_contract(principal_scope_key=provider._principal_scope_key)
        assert contract is not None
        assert int(contract["revision_number"]) == 1
        assert str(contract["content"]) == _style_contract_text().strip()
        tasks = store.list_task_items(principal_scope_key=provider._principal_scope_key, limit=10)
        assert {str(item["title"]) for item in tasks} == {
            "review the phase 40 authority plan",
            "write the phase 40 verification summary",
        }
        operating = store.list_operating_records(principal_scope_key=provider._principal_scope_key, limit=10)
        assert sorted(str(item["record_type"]) for item in operating) == [
            "active_work",
            "current_commitment",
            "next_step",
        ]
    finally:
        provider.shutdown()


def test_prefetch_self_heals_missing_compiled_policy_and_exposes_out_of_band_debug(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase40-self-heal")
    try:
        provider.sync_turn(_style_contract_text(), "ertettem", session_id="phase40-self-heal")

        store = provider._store
        assert store is not None
        contract = store.get_behavior_contract(principal_scope_key=provider._principal_scope_key)
        assert contract is not None
        store._delete_compiled_behavior_policy_record(principal_scope_key=provider._principal_scope_key)
        store.conn.commit()

        block = provider.prefetch("Mire kell figyelned a stilusomban?", session_id="phase40-self-heal")
        snapshot = provider.behavior_policy_snapshot()
        debug = provider.memory_authority_debug()

        assert snapshot is not None
        assert snapshot["compiled_policy"]["present"] is True
        assert snapshot["compiled_policy"]["source_revision_number"] == snapshot["raw_contract"]["revision_number"]
        assert debug is not None
        assert debug["compiled_policy_source_revision"] == debug["canonical_generation_revision"]
        assert debug["brainstack_packet_sections"] or debug["system_substrate_sections"]
        assert debug["host_runtime_layers_excluded"]
    finally:
        provider.shutdown()


def test_dirty_store_repair_reactivates_clean_generation_and_stops_style_residue(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase40-dirty-repair")
    try:
        provider.sync_turn(_style_contract_text(), "ertettem", session_id="phase40-dirty-repair")
        store = provider._store
        assert store is not None
        clean = store.get_behavior_contract(principal_scope_key=provider._principal_scope_key)
        assert clean is not None

        now = "2026-04-20T00:00:00Z"
        polluted_content = "[LauraTom] ird le pontosan mit kapsz meg\nA set of 27 rules for communication style and formatting."
        polluted_metadata = {
            "session_id": "phase40-dirty-repair",
            "style_contract_title": "[LauraTom] ird le pontosan mit kapsz meg",
            "style_contract_sections": [{"title": "Rules", "lines": ["A set of 27 rules for communication style and formatting."]}],
        }
        store.conn.execute(
            "UPDATE behavior_contracts SET status = ?, updated_at = ? WHERE id = ?",
            (BEHAVIOR_CONTRACT_SUPERSEDED_STATUS, now, int(clean["id"])),
        )
        store.conn.execute(
            """
            INSERT INTO behavior_contracts (
                storage_key, principal_scope_key, stable_key, category, content, source, confidence,
                metadata_json, source_contract_hash, revision_number, parent_revision_id, status, committed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{provider._principal_scope_key}::{STYLE_CONTRACT_SLOT}::2",
                provider._principal_scope_key,
                STYLE_CONTRACT_SLOT,
                "preference",
                polluted_content,
                "prefetch:style_contract_patch",
                0.9,
                json.dumps(polluted_metadata, ensure_ascii=True, sort_keys=True),
                "dirty-hash",
                2,
                int(clean["id"]),
                BEHAVIOR_CONTRACT_ACTIVE_STATUS,
                now,
                now,
            ),
        )
        store._delete_compiled_behavior_policy_record(principal_scope_key=provider._principal_scope_key)
        store.upsert_profile_item(
            stable_key="preference:communication_rules",
            category="preference",
            content="27 rules for content, language, communication, filler, and style.",
            source="tier2_transcript_rule",
            confidence=0.8,
            metadata={"session_id": "phase40-dirty-repair", "principal_scope_key": provider._principal_scope_key},
        )
        store.upsert_profile_item(
            stable_key="preference:dash_usage",
            category="preference",
            content="Do not use dash punctuation in replies.",
            source="tier2_transcript_rule",
            confidence=0.8,
            metadata={"session_id": "phase40-dirty-repair", "principal_scope_key": provider._principal_scope_key},
        )
        store.conn.commit()

        repair = provider.repair_memory_authority()
        assert repair is not None
        assert repair["quarantined_ids"]
        assert repair["reactivated_id"] == int(clean["id"])
        assert repair["compiled_policy_rebuilt"] is True
        assert repair["deactivated_profile_residue_count"] >= 2

        block = provider.prefetch("Mik az aktiv kommunikacios szabalyok?", session_id="phase40-dirty-repair")
        snapshot = provider.behavior_policy_snapshot()

        assert "27 rules for content, language, communication, filler, and style." not in block
        assert snapshot is not None
        assert snapshot["raw_contract"]["revision_number"] == 1
        assert snapshot["compiled_policy"]["source_revision_number"] == 1
    finally:
        provider.shutdown()


def test_tier2_does_not_regenerate_style_atoms_when_style_contract_is_present() -> None:
    transcript_entries = [
        {
            "turn_number": 1,
            "role": "user",
            "content": "Mostantol ez a szabalykeszlet el: ne hasznalj emojit es ne hasznalj dash jeleket.",
        }
    ]

    def _fake_llm_caller(*, task: str, messages: list, timeout: float, max_tokens: int) -> str:
        return json.dumps(
            {
                "profile_items": [],
                "style_contract": {
                    "title": "",
                    "sections": [
                        {
                            "heading": "Rules",
                            "lines": [
                                "Ne hasznalj emojit.",
                                "Ne hasznalj dash jeleket.",
                            ],
                        }
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

    result = extract_tier2_candidates(
        transcript_entries,
        llm_caller=_fake_llm_caller,
    )

    assert result["style_contract"] is not None
    assert result["profile_items"] == []
