from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_backend_parity_probe
from brainstack.operating_truth import OPERATING_RECORD_ACTIVE_WORK


PRINCIPAL_SCOPE = "principal:backend-parity"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _seed_probe_fixture(store: BrainstackStore) -> None:
    metadata = {"principal_scope_key": PRINCIPAL_SCOPE}
    store.upsert_profile_item(
        stable_key="preference:probe",
        category="preference",
        content="The probe fixture prefers scoped recall parity.",
        source="backend-parity.fixture",
        confidence=0.99,
        metadata=metadata,
    )
    store.upsert_operating_record(
        stable_key="work:probe",
        principal_scope_key=PRINCIPAL_SCOPE,
        record_type=OPERATING_RECORD_ACTIVE_WORK,
        content="The probe fixture is checking backend parity.",
        owner="user_project",
        source="backend-parity.fixture",
        metadata=metadata,
    )
    store.upsert_graph_state(
        subject_name="Probe Graph",
        attribute="status",
        value_text="parity visible",
        source="backend-parity.fixture",
        metadata=metadata,
    )


def test_backend_parity_probe_is_public_safe_and_counts_shelves(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        _seed_probe_fixture(store)
        report = build_backend_parity_probe(
            store,
            query="probe scoped parity visible",
            session_id="backend-parity-session",
            principal_scope_key=PRINCIPAL_SCOPE,
        )

        assert report["schema"] == "brainstack.backend_parity_probe.v1"
        assert report["row_counts"]["profile_items"] == 1
        assert report["row_counts"]["operating_records"] == 1
        assert report["semantic_evidence_shelf_counts"]["profile"] == 1
        assert report["semantic_evidence_shelf_counts"]["operating"] == 1
        assert report["semantic_evidence_shelf_counts"]["graph"] == 1
        assert report["selected_counts"]["profile"] >= 1
        assert report["selected_counts"]["graph"] >= 1
        serialized = json.dumps(report, ensure_ascii=False)
        assert "The probe fixture prefers scoped recall parity" not in serialized
        assert "parity visible" not in serialized
    finally:
        store.close()


def test_backend_parity_probe_script_outputs_compact_json(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        _seed_probe_fixture(store)
    finally:
        store.close()

    result = subprocess.run(
        [
            sys.executable,
            "scripts/brainstack_backend_parity_probe.py",
            "--db-path",
            str(tmp_path / "brainstack.sqlite3"),
            "--query",
            "probe scoped parity visible",
            "--principal-scope-key",
            PRINCIPAL_SCOPE,
        ],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)
    assert payload["schema"] == "brainstack.backend_parity_probe.v1"
    assert payload["selected_counts"]["profile"] >= 1
