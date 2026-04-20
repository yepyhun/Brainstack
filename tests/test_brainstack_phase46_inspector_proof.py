# ruff: noqa: E402

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="Legacy pre-phase50 contract test; current source-of-truth validates de-escalated kernel behavior in phase48/50-focused suites."
)


import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location(
    "phase46_host_import_shims",
    _host_shims_path,
)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider
from brainstack.db import (
    BEHAVIOR_CONTRACT_ACTIVE_STATUS,
    BEHAVIOR_CONTRACT_SUPERSEDED_STATUS,
    STYLE_CONTRACT_SLOT,
)


def _make_provider(tmp_path: Path, session_id: str) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        config={
            "db_path": str(tmp_path / "brainstack.db"),
            "graph_backend": "none",
            "corpus_backend": "none",
        }
    )
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


def test_inspector_proof_snapshot_shows_clean_authority_convergence(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase46-clean-authority")
    try:
        provider.sync_turn(_style_contract_text(), "ertettem", session_id="phase46-clean-authority")
        provider.prefetch("Mik az aktiv kommunikacios szabalyok?", session_id="phase46-clean-authority")

        snapshot = provider.inspector_proof_snapshot()
        report = provider.inspector_proof_report()

        assert snapshot is not None
        assert snapshot["authority"]["converged"] is True
        assert snapshot["read_surface"]["clean"] is True
        assert snapshot["routing"]["applied_mode"] == "style_contract"
        assert snapshot["routing"]["source"] == "direct_profile_slot_match"
        assert report is not None
        assert "## Authority" in report
        assert "- converged: True" in report
        assert "## Read Surface" in report
    finally:
        provider.shutdown()


def test_inspector_proof_snapshot_replays_route_failure_deterministically(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase46-route-failure")
    try:
        provider._route_resolver_override = lambda _query: (_ for _ in ()).throw(  # type: ignore[attr-defined]
            RuntimeError("Error code: 402 - This request requires more credits")
        )
        provider.prefetch("Magyarazd el roviden ezt a kodot.", session_id="phase46-route-failure")

        snapshot = provider.inspector_proof_snapshot()

        assert snapshot is not None
        assert snapshot["routing"]["applied_mode"] == "fact"
        assert snapshot["routing"]["source"] == "route_resolution_failed"
        assert snapshot["routing"]["resolution_status"] == "failed"
        assert snapshot["routing"]["resolution_error_class"] == "economic_drift"
    finally:
        provider.shutdown()


def test_inspector_proof_snapshot_tracks_dirty_store_repair_and_residue_cleanup(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase46-dirty-repair")
    try:
        provider.sync_turn(_style_contract_text(), "ertettem", session_id="phase46-dirty-repair")
        store = provider._store
        assert store is not None
        clean = store.get_behavior_contract(principal_scope_key=provider._principal_scope_key)
        assert clean is not None

        now = "2026-04-20T00:00:00Z"
        polluted_content = "[LauraTom] ird le pontosan mit kapsz meg\nA set of 27 rules for communication style and formatting."
        polluted_metadata = {
            "session_id": "phase46-dirty-repair",
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
            metadata={"session_id": "phase46-dirty-repair", "principal_scope_key": provider._principal_scope_key},
        )
        store.conn.commit()

        repair = provider.repair_memory_authority()
        provider.prefetch("Mik az aktiv kommunikacios szabalyok?", session_id="phase46-dirty-repair")
        snapshot = provider.inspector_proof_snapshot()

        assert repair is not None
        assert repair["compiled_policy_rebuilt"] is True
        assert repair["deactivated_profile_residue_count"] >= 1
        assert snapshot is not None
        assert snapshot["authority"]["converged"] is True
        assert snapshot["behavior_policy_snapshot"]["raw_contract"]["revision_number"] == 1
    finally:
        provider.shutdown()


def test_inspector_proof_snapshot_keeps_graph_skip_trace_out_of_band(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase46-graph-proof")
    try:
        provider.sync_turn(
            "Project Atlas is active now. Laura is in Budapest.",
            "Ertettem.",
            session_id="phase46-graph-proof",
        )
        snapshot = provider.inspector_proof_snapshot()
        report = provider.inspector_proof_report()

        assert snapshot is not None
        assert snapshot["graph_ingress_trace"]["status"] == "skipped_no_typed_graph_evidence"
        assert report is not None
        assert "## Graph Ingress" in report
        assert "skipped_no_typed_graph_evidence" in report
    finally:
        provider.shutdown()
