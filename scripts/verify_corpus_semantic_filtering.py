#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.corpus_backend_chroma import ChromaCorpusBackend  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402

SCHEMA = "brainstack.corpus_semantic_filtering_verifier.v1"


class _FakeSemanticBackend:
    target_name = "fake.semantic"

    def __init__(self, rows_by_where: dict[tuple[tuple[str, str], ...], list[dict[str, Any]]]) -> None:
        self.calls: list[dict[str, Any]] = []
        self.rows_by_where = rows_by_where

    def open(self) -> None:
        return None

    def close(self) -> None:
        return None

    def is_empty(self) -> bool:
        return False

    def publish_document(self, snapshot: dict[str, Any]) -> None:
        del snapshot

    def score_texts(self, *, query: str, texts: list[str]) -> list[float]:
        del query
        return [0.0 for _ in texts]

    def search_semantic(self, *, query: str, limit: int, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        del query, limit
        payload = dict(where or {})
        self.calls.append(payload)
        key = tuple(sorted((str(k), str(v)) for k, v in payload.items()))
        return [dict(row) for row in self.rows_by_where.get(key, [])]


class _FakeCollection:
    def __init__(self) -> None:
        self.upsert_kwargs: dict[str, Any] = {}

    def upsert(self, **kwargs: Any) -> None:
        self.upsert_kwargs = kwargs

    def get(self, *, where: dict[str, Any], include: list[Any]) -> dict[str, Any]:
        del where, include
        return {"ids": self.upsert_kwargs.get("ids", [])}

    def delete(self, **kwargs: Any) -> None:
        del kwargs


def _filtered_case(tmp: Path) -> dict[str, Any]:
    where = {"semantic_class": "corpus", "principal_scope_key": "principal:m008"}
    key = tuple(sorted((str(k), str(v)) for k, v in where.items()))
    backend = _FakeSemanticBackend(
        {
            key: [
                {
                    "content": "Filtered public row",
                    "metadata": {"stable_key": "doc:m008"},
                    "retrieval_source": "corpus.semantic",
                    "match_mode": "semantic",
                }
            ]
        }
    )
    store = BrainstackStore(str(tmp / "filtered.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        store._corpus_backend = backend
        rows = store.search_corpus_semantic(query="filtered", limit=4, principal_scope_key="principal:m008")
    finally:
        store.close()
    semantic_filter = rows[0].get("metadata", {}).get("semantic_filter") if rows else {}
    return {
        "case_id": "filtered_first",
        "status": "pass"
        if backend.calls == [where]
        and semantic_filter.get("requested_where") == where
        and semantic_filter.get("fallback_used") is False
        else "fail",
        "calls": backend.calls,
        "semantic_filter": semantic_filter,
    }


def _fallback_case(tmp: Path) -> dict[str, Any]:
    scoped = {"semantic_class": "corpus", "principal_scope_key": "principal:m008"}
    base = {"semantic_class": "corpus"}
    base_key = tuple(sorted((str(k), str(v)) for k, v in base.items()))
    backend = _FakeSemanticBackend(
        {
            base_key: [
                {
                    "content": "Fallback public row",
                    "metadata": {"stable_key": "doc:legacy"},
                    "retrieval_source": "corpus.semantic",
                    "match_mode": "semantic",
                }
            ]
        }
    )
    store = BrainstackStore(str(tmp / "fallback.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        store._corpus_backend = backend
        rows = store.search_corpus_semantic(query="legacy", limit=4, principal_scope_key="principal:m008")
    finally:
        store.close()
    semantic_filter = rows[0].get("metadata", {}).get("semantic_filter") if rows else {}
    return {
        "case_id": "visible_fallback",
        "status": "pass"
        if backend.calls == [scoped, base]
        and semantic_filter.get("requested_where") == scoped
        and semantic_filter.get("fallback_used") is True
        else "fail",
        "calls": backend.calls,
        "semantic_filter": semantic_filter,
    }


def _publish_metadata_case() -> dict[str, Any]:
    backend = ChromaCorpusBackend(db_path=":memory:")
    collection = _FakeCollection()
    backend._collection = collection
    backend.publish_document(
        {
            "document": {
                "id": 7,
                "stable_key": "doc:m008:filter",
                "title": "Filter proof",
                "doc_kind": "note",
                "source": "fixture://m008/filter",
                "updated_at": "2026-05-03T00:00:00Z",
                "metadata": {
                    "principal_scope_key": "principal:m008",
                    "workspace_scope_key": "workspace:m008",
                    "language": "hu",
                    "source_uri": "fixture://m008/filter",
                },
            },
            "sections": [
                {
                    "section_id": 11,
                    "section_index": 0,
                    "heading": "Filter metadata",
                    "content": "Corpus semantic filter metadata proof.",
                    "token_estimate": 9,
                    "metadata": {"language": "de", "doc_type": "note-section"},
                }
            ],
        }
    )
    metadata = dict(collection.upsert_kwargs.get("metadatas", [{}])[0])
    required = {
        "principal_scope_key": "principal:m008",
        "workspace_scope_key": "workspace:m008",
        "language": "de",
        "source_uri": "fixture://m008/filter",
        "doc_type": "note-section",
    }
    return {
        "case_id": "chroma_flat_filter_metadata",
        "status": "pass" if all(metadata.get(key) == value for key, value in required.items()) else "fail",
        "required": required,
        "observed": {key: metadata.get(key) for key in required},
    }


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-m008-corpus-filter-") as tmpdir:
        tmp = Path(tmpdir)
        cases = [_filtered_case(tmp), _fallback_case(tmp), _publish_metadata_case()]
    failures = [case["case_id"] for case in cases if case.get("status") != "pass"]
    return {
        "schema": SCHEMA,
        "status": "pass" if not failures else "fail",
        "failure_reasons": failures,
        "cases": cases,
        "public_safe": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify corpus semantic metadata filtering and visible fallback.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "failure_reasons": report["failure_reasons"]}, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
