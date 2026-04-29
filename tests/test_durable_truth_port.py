from __future__ import annotations

from pathlib import Path

import pytest

from brainstack.core.admission import SourceAuthority, TruthShelf, TruthWritePermit
from brainstack.db import BrainstackStore
from brainstack.storage.durable_truth_port import DurableTruthPort
from brainstack.storage.durable_write_guard import DurableTruthWriteViolation


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def test_direct_tier2_profile_truth_write_requires_admission_or_permit(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        with pytest.raises(DurableTruthWriteViolation):
            store.upsert_profile_item(
                stable_key="identity:preferred_address_name",
                category="identity",
                content="Alex",
                source="tier2:test",
                confidence=0.9,
                metadata={"assertion_speaker": "user"},
            )
    finally:
        store.close()


def test_durable_truth_port_profile_write_adds_typed_permit(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        permit = TruthWritePermit.trusted_explicit(
            permit_id="permit:test:explicit",
            source_authority=SourceAuthority.USER_EXPLICIT_ASSERTION,
            shelf=TruthShelf.PROFILE,
            slot="identity:preferred_address_name",
            trusted_context_id="explicit:test",
        )
        row_id = DurableTruthPort(store).write_profile(
            stable_key="identity:preferred_address_name",
            category="identity",
            content="Alex",
            source="explicit:test",
            confidence=1.0,
            permit=permit,
        )
        assert row_id > 0
        item = store.get_profile_item(stable_key="identity:preferred_address_name")
        assert item is not None
        assert item["metadata"]["truth_write_permit"]["permit_id"] == "permit:test:explicit"
        assert item["metadata"]["durable_write_context"]["write_path_class"] == "TRUSTED_EXPLICIT_CAPTURE"
    finally:
        store.close()


def test_direct_tier2_graph_truth_write_requires_admission_or_permit(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        with pytest.raises(DurableTruthWriteViolation):
            store.upsert_graph_state(
                subject_name="Assistant",
                attribute="shell_access",
                value_text="available",
                source="tier2:test",
                metadata={"source_authority": "runtime_diagnostic"},
            )
    finally:
        store.close()


def test_tier2_operating_support_allowed_but_current_assignment_blocked(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        support_id = store.upsert_operating_record(
            stable_key="support:pulse",
            principal_scope_key="principal:test",
            record_type="runtime_pulse",
            content="Pulse ran.",
            owner="brainstack.pulse",
            source="tier2:test",
            metadata={"supporting_evidence_only": True, "current_assignment_authority": False},
        )
        assert support_id > 0

        with pytest.raises(DurableTruthWriteViolation):
            store.upsert_operating_record(
                stable_key="current:assignment",
                principal_scope_key="principal:test",
                record_type="current_assignment_state",
                content="Work on Pulse.",
                owner="brainstack.operating_truth",
                source="tier2:test",
                metadata={
                    "current_assignment_authority": True,
                    "source_authority": "tier2_summary",
                },
            )
    finally:
        store.close()


def test_support_only_metadata_forces_non_model_facing(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        permit = TruthWritePermit.trusted_explicit(
            permit_id="permit:test:support",
            shelf=TruthShelf.PROFILE,
            slot="preference:formatting",
            trusted_context_id="explicit:support",
        )
        DurableTruthPort(store).write_profile(
            stable_key="preference:formatting",
            category="preference",
            content="Avoid emoji.",
            source="explicit:test",
            confidence=1.0,
            permit=permit,
            metadata={"support_visibility": "inspect_only", "truth_eligible": True},
        )
        item = store.get_profile_item(stable_key="preference:formatting")
        assert item is not None
        assert item["metadata"]["truth_eligible"] is False
        assert item["metadata"]["model_facing_default"] is False
    finally:
        store.close()
