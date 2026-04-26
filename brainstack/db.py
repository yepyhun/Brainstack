from __future__ import annotations

from .storage.store_runtime import (
    CorpusBackend,
    GraphBackend,
    Path,
    _locked,
    create_corpus_backend,
    create_graph_backend,
    logger,
    sqlite3,
    threading,
    utc_now_iso,
)
from .storage.schema_migrations import SchemaMigrationMixin
from .storage.publish_journal_store import PublishJournalStoreMixin
from .storage.continuity_store import ContinuityStoreMixin
from .storage.profile_store import ProfileStoreMixin
from .storage.task_store import TaskStoreMixin
from .storage.operating_store import OperatingStoreMixin
from .storage.profile_read_store import ProfileReadStoreMixin
from .storage.corpus_store import CorpusStoreMixin
from .storage.semantic_index_store import SemanticIndexStoreMixin
from .storage.graph_state_store import GraphStateStoreMixin
from .storage.telemetry_store import TelemetryStoreMixin

__all__ = ["BrainstackStore", "utc_now_iso"]


class BrainstackStore(
    SchemaMigrationMixin,
    PublishJournalStoreMixin,
    ContinuityStoreMixin,
    ProfileStoreMixin,
    TaskStoreMixin,
    OperatingStoreMixin,
    ProfileReadStoreMixin,
    CorpusStoreMixin,
    SemanticIndexStoreMixin,
    GraphStateStoreMixin,
    TelemetryStoreMixin,
):
    def __init__(
        self,
        db_path: str,
        *,
        graph_backend: str = "sqlite",
        graph_db_path: str | None = None,
        corpus_backend: str = "sqlite",
        corpus_db_path: str | None = None,
    ) -> None:
        self._db_path = str(db_path)
        self._graph_backend_name = str(graph_backend or "sqlite").strip().lower()
        default_graph_db = str(Path(self._db_path).with_suffix(".kuzu"))
        self._graph_db_path = str(graph_db_path or default_graph_db)
        self._corpus_backend_name = str(corpus_backend or "sqlite").strip().lower()
        default_corpus_db = str(Path(self._db_path).with_suffix(".chroma"))
        self._corpus_db_path = str(corpus_db_path or default_corpus_db)
        self._conn: sqlite3.Connection | None = None
        self._graph_backend: GraphBackend | None = None
        self._graph_backend_error = ""
        self._corpus_backend: CorpusBackend | None = None
        self._corpus_backend_error = ""
        self._lock = threading.RLock()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("BrainstackStore is not open")
        return self._conn

    @_locked
    def open(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()
        self._backfill_legacy_principal_scoped_profiles_if_needed()
        self._run_compatibility_migrations_if_needed()
        try:
            self._graph_backend = create_graph_backend(self._graph_backend_name, db_path=self._graph_db_path)
            if self._graph_backend is None and self._graph_backend_name not in {"", "none", "sqlite"}:
                self._graph_backend_error = (
                    f"Graph backend {self._graph_backend_name!r} was requested but no backend adapter is active."
                )
            if self._graph_backend is not None:
                self._graph_backend.open()
                self._graph_backend_error = ""
                self._bootstrap_graph_backend_if_needed()
        except ModuleNotFoundError as exc:
            self._disable_graph_backend(reason=str(exc))
        except Exception as exc:
            logger.warning(
                "Brainstack graph backend unavailable; disabling graph backend and continuing with SQLite: %s",
                exc,
            )
            self._disable_graph_backend(reason=str(exc))
        self._corpus_backend = create_corpus_backend(self._corpus_backend_name, db_path=self._corpus_db_path)
        if self._corpus_backend is not None:
            try:
                self._corpus_backend.open()
            except ModuleNotFoundError as exc:
                self._corpus_backend_error = str(exc)
                self._corpus_backend = None
            else:
                self._corpus_backend_error = ""
                self._bootstrap_corpus_backend_if_needed()
                self._replay_corpus_publications_if_needed()

    @_locked
    def close(self) -> None:
        if self._corpus_backend is not None:
            self._corpus_backend.close()
            self._corpus_backend = None
        if self._graph_backend is not None:
            self._graph_backend.close()
            self._graph_backend = None
        if self._conn is not None:
            self._conn.close()
            self._conn = None
