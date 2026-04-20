# ruff: noqa: E402

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
    "phase47_host_import_shims",
    _host_shims_path,
)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider
from brainstack.extraction_pipeline import build_turn_ingest_plan


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


def test_explicit_graph_ingest_surfaces_exact_value_without_live_text_guessing(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase47-explicit-graph")
    try:
        result = provider.ingest_graph_evidence(
            evidence_items=[
                {
                    "kind": "state",
                    "subject": "Móni",
                    "attribute": "address",
                    "value_text": "Kassák Lajos 87 44es kapucsengő 4em",
                    "confidence": 0.91,
                    "language": "hu",
                    "provenance_class": "producer:typed_graph",
                }
            ],
            source="producer:typed_graph",
            session_id="phase47-explicit-graph",
            turn_number=1,
        )

        rows = provider._store.search_graph(query="Móni Kassák", limit=10)
        assert result["receipt"]["accepted_count"] == 1
        assert result["receipt"]["written_count"] == 1
        assert any(
            row["row_type"] == "state"
            and row["subject"] == "Móni"
            and row["predicate"] == "address"
            and "Kassák Lajos 87" in row["object_value"]
            for row in rows
        )
        assert provider.graph_ingress_trace()["surface"] == "explicit_graph_ingress"
    finally:
        provider.shutdown()


def test_multimodal_memory_artifact_links_corpus_and_graph_with_shared_document_id(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, "phase47-multimodal")
    try:
        result = provider.ingest_multimodal_memory_artifact(
            title="Masszazs kartya foto",
            content="Móni talpmasszázs. Cím: Kassák Lajos 87 44es kapucsengő 4em.",
            source="vision:ocr_document",
            modality="document_image",
            graph_evidence_items=[
                {
                    "kind": "state",
                    "subject": "Móni",
                    "attribute": "address",
                    "value_text": "Kassák Lajos 87 44es kapucsengő 4em",
                    "confidence": 0.86,
                    "language": "hu",
                    "provenance_class": "producer:vision_ocr",
                }
            ],
            session_id="phase47-multimodal",
            turn_number=2,
        )

        corpus_rows = provider._store.search_corpus(query="Kassák", limit=10)
        graph_rows = provider._store.search_graph(query="Móni Kassák", limit=10)
        source_document_id = result["source_document_id"]
        document_id = int(result["corpus_document"]["document_id"])
        metadata_row = provider._store.conn.execute(
            "SELECT metadata_json FROM corpus_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        assert metadata_row is not None
        document_metadata = json.loads(str(metadata_row["metadata_json"] or "{}"))

        assert result["modality"] == "document_image"
        assert result["graph_ingress"]["receipt"]["accepted_count"] == 1
        assert any(row["title"] == "Masszazs kartya foto" for row in corpus_rows)
        assert document_metadata.get("modality") == "document_image"
        assert any(
            row["row_type"] == "state"
            and row["metadata"].get("graph_evidence", {}).get("source_document_id") == source_document_id
            for row in graph_rows
        )
    finally:
        provider.shutdown()


def test_live_turn_ingest_remains_fail_closed_without_explicit_typed_evidence() -> None:
    plan = build_turn_ingest_plan(
        user_content="Project Atlas is active now. Laura is in Budapest.",
        pending_turns=0,
        idle_seconds=60.0,
        idle_window_seconds=30,
        batch_turn_limit=5,
    )

    assert plan.graph_evidence_items == []
