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
    "phase48_host_import_shims",
    _host_shims_path,
)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider  # noqa: E402
from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from brainstack.db import (  # noqa: E402
    BEHAVIOR_CONTRACT_ACTIVE_STATUS,
    BEHAVIOR_CONTRACT_SUPERSEDED_STATUS,
    BrainstackStore,
    STYLE_CONTRACT_SLOT,
)


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


def test_prefetch_bootstraps_authority_before_packet_build(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase48-prefetch-bootstrap")
    try:
        provider.sync_turn(_style_contract_text(), "ertettem", session_id="phase48-prefetch-bootstrap")
        store = provider._store
        assert store is not None

        clean = store.get_behavior_contract(principal_scope_key=provider._principal_scope_key)
        assert clean is not None
        now = "2026-04-20T00:00:00Z"
        polluted_content = (
            "[LauraTom] ird le pontosan mit kapsz meg mast ne!\n"
            "A set of 27 rules for communication style and formatting."
        )
        polluted_metadata = {
            "session_id": "phase48-prefetch-bootstrap",
            "style_contract_title": "[LauraTom] ird le pontosan mit kapsz meg mast ne!",
            "style_contract_sections": [
                {
                    "title": "Rules",
                    "lines": ["A set of 27 rules for communication style and formatting."],
                }
            ],
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
        store.conn.commit()

        provider.prefetch(
            "Miért nem tartod be a szabályokat? Nem emlékszel rájuk?",
            session_id="phase48-prefetch-bootstrap",
        )

        snapshot = provider.behavior_policy_snapshot()
        trace = provider.behavior_policy_trace()
        debug = provider.memory_authority_debug()

        assert snapshot is not None
        assert snapshot["raw_contract"]["revision_number"] == 1
        assert snapshot["compiled_policy"]["present"] is True
        assert snapshot["compiled_policy"]["source_revision_number"] == 1
        assert trace is not None
        assert trace["authority_bootstrap"]["prefetch"]["repair_attempted"] is True
        assert trace["authority_bootstrap"]["prefetch"]["blocked"] is False
        assert debug is not None
        assert debug["authority_bootstrap"]["repair_attempted"] is True
    finally:
        provider.shutdown()


def test_final_output_blocks_when_active_authority_cannot_rebuild(monkeypatch, tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase48-block-on-missing-compiled")
    try:
        store = provider._store
        assert store is not None
        store.upsert_behavior_contract(
            category="preference",
            content=_style_contract_text(),
            source="test",
            confidence=1.0,
            metadata={"principal_scope_key": provider._principal_scope_key},
        )
        store._delete_compiled_behavior_policy_record(principal_scope_key=provider._principal_scope_key)
        store.conn.commit()

        monkeypatch.setattr(
            store,
            "_ensure_compiled_behavior_policy_for_contract_item",
            lambda _contract_item: False,
        )

        result = provider.validate_assistant_output("Szia 😊")
        assert result is not None
        assert result["status"] == "blocked"
        assert result["blocked"] is True
        assert result["can_ship"] is False
        assert result["block_reason"] == "compiled_behavior_policy_unavailable"
        assert result["remaining_violations"][0]["violation"] == "compiled_policy_missing_for_active_authority"
    finally:
        provider.shutdown()


def test_natural_hungarian_rule_recall_routes_to_style_authority(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    try:
        store.upsert_profile_item(
            category="preference",
            content=_style_contract_text(),
            stable_key=STYLE_CONTRACT_SLOT,
            source="test",
            confidence=1.0,
        )
        packet = build_working_memory_packet(
            store,
            query="Miért nem tartod be a szabályokat? Nem emlékszel rájuk?",
            session_id="phase48-natural-style-recall",
            principal_scope_key="",
            profile_match_limit=4,
            continuity_recent_limit=4,
            continuity_match_limit=4,
            transcript_match_limit=2,
            transcript_char_budget=560,
            graph_limit=6,
            corpus_limit=4,
            corpus_char_budget=700,
        )

        assert packet["routing"]["requested_mode"] == "style_contract"
        assert packet["routing"]["applied_mode"] == "style_contract"
        assert packet["routing"]["source"] == "deterministic_style_contract_hint"
        assert packet["policy"]["show_authoritative_contract"] is True
    finally:
        store.close()
