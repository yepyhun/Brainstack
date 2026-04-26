from __future__ import annotations

import json
from pathlib import Path

import pytest

from brainstack import BrainstackMemoryProvider
from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.explicit_truth_parity import (
    DIVERGENCE_CONTENT_CONFLICT,
    DIVERGENCE_CURRENT_PRIOR_MISMATCH,
    DIVERGENCE_DERIVED_PARTIAL,
    DIVERGENCE_SCOPE_MISMATCH,
    OBSERVABLE_CLEAN,
    OBSERVABLE_DIVERGED,
    PARTIALLY_OBSERVABLE,
    PROJECTION_COMMITTED,
    PROJECTION_PENDING,
    build_explicit_truth_parity,
    content_hash,
)

PRINCIPAL_SCOPE = "principal:mirror-parity"


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "parity-session",
        platform="test",
        user_id="user",
        agent_identity="agent",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def test_native_profile_mirror_with_host_receipt_records_clean_parity(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        provider.on_memory_write(
            "add",
            "user",
            "User likes receipt-backed mirror parity.",
            metadata={"host_receipt_id": "host-receipt-1", "principal_scope_key": provider._principal_scope_key},
        )

        rows = provider._store.search_profile(
            query="receipt-backed mirror parity",
            limit=4,
            principal_scope_key=provider._principal_scope_key,
        )
        parity = rows[0]["metadata"]["explicit_truth_parity"]

        assert parity["host_receipt_id"] == "host-receipt-1"
        assert parity["projection_status"] == PROJECTION_COMMITTED
        assert parity["parity_observable"] == OBSERVABLE_CLEAN
        assert parity["divergence_status"] == "none"
        assert parity["brainstack_projection_receipt_id"]
    finally:
        provider.shutdown()


def test_native_profile_mirror_without_host_receipt_is_derived_partial_not_clean(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        provider.on_memory_write(
            "add",
            "user",
            "User likes derived mirror trace visibility.",
            metadata={"principal_scope_key": provider._principal_scope_key},
        )

        rows = provider._store.search_profile(
            query="derived mirror trace visibility",
            limit=4,
            principal_scope_key=provider._principal_scope_key,
        )
        parity = rows[0]["metadata"]["explicit_truth_parity"]

        assert parity["host_receipt_source"] == "derived_host_trace"
        assert parity["divergence_status"] == DIVERGENCE_DERIVED_PARTIAL
        assert parity["parity_observable"] == PARTIALLY_OBSERVABLE
    finally:
        provider.shutdown()


def test_failed_projection_receipt_does_not_become_committed(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        with pytest.raises(RuntimeError):
            provider._commit_explicit_write(
                owner="test",
                write_class="explicit_test",
                source="test",
                target="profile",
                stable_key="parity:failed",
                category="preference",
                content="failed projection",
                commit=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
                extra={"host_receipt_id": "host-failed"},
            )
        receipt = provider.memory_operation_trace()["last_write_receipt"]
        assert receipt["status"] == "failed"
        assert receipt["explicit_truth_parity"]["projection_status"] == "failed"
        assert receipt["explicit_truth_parity"]["parity_observable"] == OBSERVABLE_DIVERGED
    finally:
        provider.shutdown()


def test_parity_detects_scope_stable_key_content_and_supersession_mismatch() -> None:
    scope = build_explicit_truth_parity(
        projection_status=PROJECTION_COMMITTED,
        stable_key="truth:key",
        principal_scope_key="scope:b",
        content="same",
        host_receipt_id="host-1",
        host_scope="scope:a",
    )
    content = build_explicit_truth_parity(
        projection_status=PROJECTION_COMMITTED,
        stable_key="truth:key",
        principal_scope_key="scope:a",
        content="brainstack",
        host_receipt_id="host-2",
        host_content_hash=content_hash("host"),
    )
    supersession = build_explicit_truth_parity(
        projection_status=PROJECTION_COMMITTED,
        stable_key="truth:key",
        principal_scope_key="scope:a",
        content="same",
        host_receipt_id="host-3",
        host_temporal_status="prior",
        brainstack_temporal_status="current",
    )

    assert scope["divergence_status"] == DIVERGENCE_SCOPE_MISMATCH
    assert scope["parity_observable"] == OBSERVABLE_DIVERGED
    assert content["divergence_status"] == DIVERGENCE_CONTENT_CONFLICT
    assert supersession["divergence_status"] == DIVERGENCE_CURRENT_PRIOR_MISMATCH


def test_pending_projection_barrier_degrades_answerability(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        parity = build_explicit_truth_parity(
            projection_status=PROJECTION_PENDING,
            stable_key="debug:marker",
            principal_scope_key=PRINCIPAL_SCOPE,
            content="Debug marker is 1231231X.",
            host_receipt_id="host-pending",
        )
        store.upsert_profile_item(
            stable_key="debug:marker",
            category="preference",
            content="Debug marker is 1231231X.",
            source="parity.fixture",
            confidence=0.99,
            metadata={"principal_scope_key": PRINCIPAL_SCOPE, "explicit_truth_parity": parity},
        )

        report = build_query_inspect(
            store,
            query="debug marker 1231231X",
            session_id="parity-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            profile_match_limit=4,
            continuity_match_limit=0,
            continuity_recent_limit=0,
            transcript_match_limit=0,
            operating_match_limit=0,
            graph_limit=0,
            corpus_limit=0,
        )

        assert report["selected_evidence"]["profile"][0]["explicit_truth_parity"]["projection_status"] == PROJECTION_PENDING
        assert report["memory_answerability"]["can_answer"] is False
        assert report["memory_answerability"]["reason_code"] == "PENDING_WRITE_BARRIER"
        assert report["memory_answerability"]["answer_evidence_ids"] == []
    finally:
        store.close()


def test_recall_tool_surfaces_explicit_truth_parity(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        provider.on_memory_write(
            "add",
            "user",
            "User likes recall parity cards.",
            metadata={"host_receipt_id": "host-recall", "principal_scope_key": provider._principal_scope_key},
        )
        payload = json.loads(provider.handle_tool_call("brainstack_recall", {"query": "recall parity cards"}))
        profile_rows = payload["selected_evidence"]["profile"]

        assert profile_rows
        assert profile_rows[0]["explicit_truth_parity"]["host_receipt_id"] == "host-recall"
        assert payload["final_packet"]["explicit_truth_parity"][0]["host_receipt_id"] == "host-recall"
    finally:
        provider.shutdown()
