from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.persistent_bloat_rebuild import (
    PERSISTENT_BLOAT_REBUILD_PROOF_SCHEMA,
    verify_persistent_bloat_rebuild,
)
from scripts.run_persistent_bloat_soak import PRIVATE_SOAK_SENTINEL, seed_persistent_bloat_soak

ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = ROOT / "scripts" / "verify_persistent_bloat_rebuild.py"


def _store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"))
    store.open()
    seed_persistent_bloat_soak(store, iterations=12)
    return store


def test_persistent_bloat_rebuild_preserves_answer_safe_snapshot_after_maintenance(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        proof = verify_persistent_bloat_rebuild(store)
    finally:
        store.close()

    rendered = json.dumps(proof, ensure_ascii=False, sort_keys=True)
    assert PRIVATE_SOAK_SENTINEL not in rendered
    assert proof["schema"] == PERSISTENT_BLOAT_REBUILD_PROOF_SCHEMA
    assert proof["status"] == "pass"
    assert proof["public_safe"] is True
    assert proof["issues"] == []
    assert proof["mismatches"] == []
    assert proof["before"]["answer_safe_ids"] == proof["after_rejected_bloat_apply"]["answer_safe_ids"]
    assert proof["before"]["answer_safe_ids"] == proof["after_semantic_index_apply"]["answer_safe_ids"]
    assert proof["before"]["authority_critical_ids"] == proof["after_semantic_index_apply"]["authority_critical_ids"]
    assert proof["critical_counters"]["projection_rebuild_mismatch"] == 0
    assert proof["critical_counters"]["authority_critical_dropped"] == 0


def test_support_prior_and_conflict_events_stay_non_answer_safe(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        proof = verify_persistent_bloat_rebuild(store)
    finally:
        store.close()

    before = proof["before"]
    answer_safe = set(before["answer_safe_ids"])
    support_only = set(before["support_only_ids"])
    prior = set(before["prior_ids"])
    conflicted = set(before["conflicted_ids"])
    assert support_only
    assert conflicted
    assert answer_safe.isdisjoint(support_only)
    assert answer_safe.isdisjoint(prior)
    assert answer_safe.isdisjoint(conflicted)
    for event_id in support_only:
        assert "projection_support_only" in before["reason_codes_by_event"][event_id]
    for event_id in conflicted:
        assert any("conflict" in reason for reason in before["reason_codes_by_event"][event_id])


def test_persistent_bloat_rebuild_cli_writes_public_safe_artifact(tmp_path: Path) -> None:
    out = tmp_path / "rebuild-proof.json"
    proc = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--iterations", "10", "--out", str(out)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["schema"] == "brainstack.persistent_bloat_rebuild_cli.v1"
    assert summary["status"] == "pass"
    assert summary["public_safe"] is True
    payload = json.loads(out.read_text(encoding="utf-8"))
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert PRIVATE_SOAK_SENTINEL not in rendered
    assert payload["proof"]["maintenance"]["persistent_bloat_apply_status"] == "rejected"
    assert "persistent_bloat_cleanup_requires_explicit_review" in payload["proof"]["maintenance"]["persistent_bloat_no_op_reasons"]
    assert payload["proof"]["maintenance"]["persistent_bloat_preservation_contract"]["truth_mutation"] is False


def test_projection_rebuild_fails_if_answer_safe_snapshot_changes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        before = verify_persistent_bloat_rebuild(store)["before"]
        target = before["answer_safe_ids"][0]
        row = store.conn.execute("SELECT event_json FROM canonical_memory_events WHERE event_id = ?", (target,)).fetchone()
        event = json.loads(row["event_json"])
        event["authority"]["support_visibility"] = "normal"
        event["authority"]["truth_eligible"] = False
        store.conn.execute(
            "UPDATE canonical_memory_events SET support_visibility = 'normal', truth_eligible = 0, event_json = ? WHERE event_id = ?",
            (json.dumps(event, ensure_ascii=True, sort_keys=True), target),
        )
        store.conn.commit()
        after = verify_persistent_bloat_rebuild(store)["before"]
    finally:
        store.close()

    assert target in before["answer_safe_ids"]
    assert target not in after["answer_safe_ids"]
