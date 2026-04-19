from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from tests._host_import_shims import install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider
from brainstack.db import BrainstackStore
from brainstack.graph import ingest_graph_evidence_with_receipt
from brainstack.graph_evidence import (
    GraphEvidenceIngressError,
    GraphEvidenceItem,
    prepare_graph_evidence_ingress,
)


def test_prepare_graph_evidence_ingress_binds_context_and_emits_receipt():
    prepared = prepare_graph_evidence_ingress(
        [
            GraphEvidenceItem(
                kind="state",
                subject="Project Atlas",
                attribute="status",
                value_text="active",
                confidence=0.9,
            )
        ],
        session_id="phase39",
        turn_number=7,
        source_document_id="doc-1",
        strict=True,
    )

    assert prepared["receipt"]["status"] == "accepted"
    assert prepared["receipt"]["accepted_count"] == 1
    assert prepared["receipt"]["rejected_count"] == 0
    item = prepared["items"][0]
    assert item.source_turn_id == "phase39:7"
    assert item.source_document_id == "doc-1"


def test_ingest_graph_evidence_with_receipt_fails_closed_on_invalid_mixed_batch(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"), graph_backend="none", corpus_backend="none")
    store.open()
    try:
        try:
            ingest_graph_evidence_with_receipt(
                store,
                evidence_items=[
                    {
                        "kind": "state",
                        "subject": "Project Atlas",
                        "attribute": "status",
                        "value_text": "active",
                        "confidence": 0.9,
                    },
                    {"kind": "state", "subject": "Project Atlas", "confidence": 0.7},
                ],
                source="test",
                metadata={"session_id": "phase39"},
            )
            raised = False
        except GraphEvidenceIngressError as exc:
            raised = True
            assert exc.receipt["status"] == "rejected"
            assert exc.receipt["accepted_count"] == 1
            assert exc.receipt["rejected_count"] == 1
            assert "state graph evidence requires attribute" in exc.receipt["rejected_items"][0]["error"]
        assert raised
        assert store.search_graph(query="Project Atlas", limit=5) == []
    finally:
        store.close()


def test_provider_sync_turn_records_graph_ingress_trace(tmp_path):
    provider = BrainstackMemoryProvider(
        config={
            "db_path": str(tmp_path / "brainstack.db"),
            "graph_backend": "none",
            "corpus_backend": "none",
        }
    )
    provider.initialize("phase39-graph-trace", hermes_home=str(tmp_path))
    try:
        provider.sync_turn(
            "Project Atlas is active now. Laura is in Budapest.",
            "Noted.",
            session_id="phase39-graph-trace",
        )

        trace = provider.graph_ingress_trace()
        assert trace is not None
        assert trace["surface"] == "sync_turn_graph_ingress"
        assert trace["status"] == "committed"
        receipt = trace["receipt"]
        assert receipt["accepted_count"] >= 2
        assert receipt["rejected_count"] == 0
        assert provider._store is not None
        rows = provider._store.search_graph(query="Project Atlas", limit=5)
        assert rows
    finally:
        provider.shutdown()
