from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from brainstack.corpus_backend_chroma import ChromaCorpusBackend
from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_memory_kernel_doctor
from scripts import brainstack_doctor


class RaisingCorpusBackend:
    target_name = "corpus.chroma"

    def __init__(self, *, reason: str) -> None:
        self.reason = reason
        self.closed = False

    def open(self) -> None:
        raise RuntimeError(self.reason)

    def close(self) -> None:
        self.closed = True


class OpenRepairEventBackend:
    target_name = "corpus.chroma"

    def __init__(self) -> None:
        self.repair_events = [
            {
                "schema": "brainstack.chroma_repair_event.v1",
                "reason_code": "CHROMA_STORE_CORRUPT_QUARANTINED",
                "operation": "open",
            }
        ]

    def open(self) -> None:
        return None

    def close(self) -> None:
        return None

    def is_empty(self) -> bool:
        return False

    def publish_document(self, snapshot: dict[str, Any]) -> None:
        return None

    def search_semantic(self, *, query: str, limit: int, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return []

    def score_texts(self, *, query: str, texts: list[str]) -> list[float]:
        return [0.0 for _ in texts]


class FakeCollection:
    def __init__(self) -> None:
        self.count_value = 0

    def count(self) -> int:
        return self.count_value


class FakePersistentClient:
    def __init__(self, **kwargs: Any) -> None:
        path = kwargs.get("path")
        if path:
            Path(str(path)).mkdir(parents=True, exist_ok=True)
        self.collection = FakeCollection()

    def get_or_create_collection(self, **_: Any) -> FakeCollection:
        return self.collection


class CorruptionAwareFakePersistentClient(FakePersistentClient):
    def __init__(self, **kwargs: Any) -> None:
        path = Path(str(kwargs.get("path") or ""))
        sqlite_path = path / "chroma.sqlite3"
        if sqlite_path.exists() and sqlite_path.read_bytes()[:16] != b"SQLite format 3\x00":
            raise sqlite3.DatabaseError("file is not a database")
        super().__init__(**kwargs)
        sqlite_path.write_bytes(b"SQLite format 3\x00" + b"\0" * 64)


class RuntimeCorruptionFakeCollection(FakeCollection):
    failed_once = False

    def count(self) -> int:
        if not RuntimeCorruptionFakeCollection.failed_once:
            RuntimeCorruptionFakeCollection.failed_once = True
            raise sqlite3.DatabaseError("Database error: file is not a database")
        return super().count()


class RuntimeCorruptionFakePersistentClient(FakePersistentClient):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        path = kwargs.get("path")
        if path:
            (Path(str(path)) / "chroma.sqlite3").write_bytes(b"SQLite format 3\x00" + b"\0" * 64)
        self.collection = RuntimeCorruptionFakeCollection()


class FakeSettings:
    def __init__(self, **_: Any) -> None:
        return None


class FakeChromaModule:
    PersistentClient = FakePersistentClient

    class utils:
        class embedding_functions:
            @staticmethod
            def DefaultEmbeddingFunction() -> Any:
                raise AssertionError("default embedding must not be used in this fixture")


class FakeEmbeddingClient:
    fingerprint = "b" * 64

    def collection_metadata(self) -> dict[str, str]:
        return {
            "brainstack:embedding_provider": "tei",
            "brainstack:embedding_model": "test",
            "brainstack:embedding_fingerprint": self.fingerprint,
        }


class FakeChromaBackend(ChromaCorpusBackend):
    def __init__(self, *, db_path: str, embedding_client: FakeEmbeddingClient | None) -> None:
        super().__init__(db_path=db_path)
        self.fake_embedding_client = embedding_client

    def _import_chromadb(self) -> tuple[Any, Any]:
        return FakeChromaModule, FakeSettings

    def _build_embedding_client(self) -> FakeEmbeddingClient | None:
        return self.fake_embedding_client


def test_store_degrades_configured_corpus_backend_on_runtime_open_error(monkeypatch, tmp_path: Path) -> None:
    backend = RaisingCorpusBackend(reason="embedding endpoint unavailable")
    monkeypatch.setattr("brainstack.db.create_corpus_backend", lambda *_args, **_kwargs: backend)

    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="chroma")
    store.open()
    try:
        assert store._corpus_backend is None
        assert backend.closed is True
        assert "embedding endpoint unavailable" in store._corpus_backend_error

        report = build_memory_kernel_doctor(
            store,
            strict=True,
            tier2_state={"enabled": False, "running": False},
        )
        corpus = report["capabilities"]["corpus"]
        assert report["verdict"] == "fail"
        assert corpus["status"] == "degraded"
        assert corpus["sqlite_fallback_active"] is True
        assert corpus["error_class"] == "backend_unavailable"
    finally:
        store.close()


def test_store_reports_configured_corpus_backend_when_adapter_is_absent(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("brainstack.db.create_corpus_backend", lambda *_args, **_kwargs: None)

    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="chroma")
    store.open()
    try:
        assert store._corpus_backend is None
        assert "requested but no backend adapter is active" in store._corpus_backend_error
    finally:
        store.close()


def test_chroma_backend_valid_embedding_first_run_creates_path(tmp_path: Path) -> None:
    chroma_path = tmp_path / "brainstack.chroma"
    backend = FakeChromaBackend(db_path=str(chroma_path), embedding_client=FakeEmbeddingClient())

    backend.open()
    try:
        assert chroma_path.exists()
        assert backend._collection is not None
    finally:
        backend.close()


def test_chroma_backend_quarantines_corrupt_cache_and_reopens(tmp_path: Path) -> None:
    chroma_path = tmp_path / "brainstack.chroma"
    chroma_path.mkdir()
    (chroma_path / "chroma.sqlite3").write_bytes(b"SQLit\x17\x03\x03not-a-sqlite-db")

    class RecoveringChromaModule(FakeChromaModule):
        PersistentClient = CorruptionAwareFakePersistentClient

    class RecoveringChromaBackend(FakeChromaBackend):
        def _import_chromadb(self) -> tuple[Any, Any]:
            return RecoveringChromaModule, FakeSettings

    backend = RecoveringChromaBackend(db_path=str(chroma_path), embedding_client=FakeEmbeddingClient())

    backend.open()
    try:
        assert backend._collection is not None
        assert (chroma_path / "chroma.sqlite3").read_bytes()[:16] == b"SQLite format 3\x00"
        quarantine_dirs = sorted(tmp_path.glob("brainstack.chroma.corrupt-*"))
        assert len(quarantine_dirs) == 1
        assert (quarantine_dirs[0] / "chroma.sqlite3").read_bytes().startswith(b"SQLit\x17\x03\x03")
        assert backend.repair_events
        assert backend.repair_events[0]["reason_code"] == "CHROMA_STORE_CORRUPT_QUARANTINED"
    finally:
        backend.close()


def test_chroma_backend_repairs_runtime_corruption_once_and_retries(tmp_path: Path) -> None:
    chroma_path = tmp_path / "brainstack.chroma"
    RuntimeCorruptionFakeCollection.failed_once = False

    class RuntimeRepairChromaModule(FakeChromaModule):
        PersistentClient = RuntimeCorruptionFakePersistentClient

    class RuntimeRepairChromaBackend(FakeChromaBackend):
        def _import_chromadb(self) -> tuple[Any, Any]:
            return RuntimeRepairChromaModule, FakeSettings

    backend = RuntimeRepairChromaBackend(db_path=str(chroma_path), embedding_client=FakeEmbeddingClient())
    backend.open()
    try:
        assert backend.is_empty() is True
        assert backend.repair_events
        assert backend.repair_events[0]["operation"] == "is_empty"
        assert sorted(tmp_path.glob("brainstack.chroma.corrupt-*"))
    finally:
        backend.close()


def test_store_reports_chroma_repair_events_after_open(monkeypatch, tmp_path: Path) -> None:
    backend = OpenRepairEventBackend()
    monkeypatch.setattr("brainstack.db.create_corpus_backend", lambda *_args, **_kwargs: backend)

    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="chroma")
    store.open()
    try:
        report = build_memory_kernel_doctor(
            store,
            strict=True,
            tier2_state={"enabled": False, "running": False},
        )
        corpus = report["capabilities"]["corpus"]
        assert corpus["status"] == "active"
        assert corpus["repair_event_count"] == 1
        assert corpus["repair_events"][0]["reason_code"] == "CHROMA_STORE_CORRUPT_QUARANTINED"
    finally:
        store.close()


def test_doctor_chroma_probe_uses_brainstack_embedding_semantics(monkeypatch, tmp_path: Path) -> None:
    def fake_probe(_code, **_kwargs):
        return {
            "path": str(tmp_path / "brainstack.chroma"),
            "exists": False,
            "openable": False,
            "error": "Chroma default embedding is disabled. Configure local TEI.",
            "error_class": "backend_embedding_config_missing",
        }

    monkeypatch.setattr(brainstack_doctor, "_run_python_probe", fake_probe)

    checks = brainstack_doctor._backend_openability_checks(
        backend="chroma",
        configured_path=str(tmp_path / "brainstack.chroma"),
        config_path=tmp_path / "config.yaml",
        planned_install=False,
        python_bin=None,
        runtime="local",
        compose_path=None,
    )

    assert checks == [
        brainstack_doctor.Check(
            "corpus_backend_open",
            "warn",
            f"chroma backend is configured but unavailable at {tmp_path / 'brainstack.chroma'}: embedding config is missing or default embeddings are disabled",
        )
    ]


def test_doctor_chroma_probe_reports_auto_repair_without_blocking(monkeypatch, tmp_path: Path) -> None:
    def fake_probe(_code, **_kwargs):
        return {
            "path": str(tmp_path / "brainstack.chroma"),
            "exists": True,
            "openable": True,
            "repair_events": [{"reason_code": "CHROMA_STORE_CORRUPT_QUARANTINED"}],
        }

    monkeypatch.setattr(brainstack_doctor, "_run_python_probe", fake_probe)

    checks = brainstack_doctor._backend_openability_checks(
        backend="chroma",
        configured_path=str(tmp_path / "brainstack.chroma"),
        config_path=tmp_path / "config.yaml",
        planned_install=False,
        python_bin=None,
        runtime="local",
        compose_path=None,
    )

    assert checks == [
        brainstack_doctor.Check(
            "corpus_backend_open",
            "pass",
            f"chroma backend opened successfully at {tmp_path / 'brainstack.chroma'} after quarantining a corrupt derived cache",
        )
    ]


def test_doctor_local_kuzu_lock_warns_only_with_active_gateway_owner(monkeypatch, tmp_path: Path) -> None:
    def fake_probe(*_args, **_kwargs):
        return {
            "path": str(tmp_path / "brainstack.kuzu"),
            "exists": True,
            "openable": False,
            "error": "IO exception: Could not set lock on file : brainstack.kuzu",
            "error_class": "RuntimeError",
        }

    monkeypatch.setattr(brainstack_doctor, "_run_python_probe", fake_probe)
    monkeypatch.setattr(brainstack_doctor, "_gateway_process_owns_path", lambda path: True)

    checks = brainstack_doctor._backend_openability_checks(
        backend="kuzu",
        configured_path=str(tmp_path / "brainstack.kuzu"),
        config_path=tmp_path / "config.yaml",
        planned_install=False,
        python_bin=None,
        runtime="local",
        compose_path=None,
    )

    assert checks == [
        brainstack_doctor.Check(
            "graph_backend_open",
            "warn",
            f"kuzu backend external probe is blocked by the active runtime owner at {tmp_path / 'brainstack.kuzu'}; dependency import and runtime health must be checked separately",
        )
    ]


def test_doctor_local_kuzu_lock_fails_without_owner_evidence(monkeypatch, tmp_path: Path) -> None:
    def fake_probe(*_args, **_kwargs):
        return {
            "path": str(tmp_path / "brainstack.kuzu"),
            "exists": True,
            "openable": False,
            "error": "IO exception: Could not set lock on file : brainstack.kuzu",
            "error_class": "RuntimeError",
        }

    monkeypatch.setattr(brainstack_doctor, "_run_python_probe", fake_probe)
    monkeypatch.setattr(brainstack_doctor, "_gateway_process_owns_path", lambda path: False)

    checks = brainstack_doctor._backend_openability_checks(
        backend="kuzu",
        configured_path=str(tmp_path / "brainstack.kuzu"),
        config_path=tmp_path / "config.yaml",
        planned_install=False,
        python_bin=None,
        runtime="local",
        compose_path=None,
    )

    assert checks == [
        brainstack_doctor.Check(
            "graph_backend_open",
            "fail",
            f"kuzu backend exists but cannot be opened at {tmp_path / 'brainstack.kuzu'}: RuntimeError: IO exception: Could not set lock on file : brainstack.kuzu",
        )
    ]
