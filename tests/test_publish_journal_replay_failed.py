from __future__ import annotations

from brainstack.db import BrainstackStore, utc_now_iso


class _FakeCorpusBackend:
    target_name = "corpus.fake"

    def __init__(self) -> None:
        self.published: list[dict] = []

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def is_empty(self) -> bool:
        return False

    def publish_document(self, snapshot: dict) -> None:
        self.published.append(snapshot)

    def search_semantic(self, *, query: str, limit: int, where: dict | None = None) -> list[dict]:
        return []

    def score_texts(self, *, query: str, texts: list[str]) -> list[float]:
        return [0.0 for _ in texts]


def _store_with_transcript_journal(tmp_path, *, status: str):
    store = BrainstackStore(
        str(tmp_path / "brainstack.db"),
        graph_backend="sqlite",
        corpus_backend="none",
    )
    store.open()
    transcript_id = store.add_transcript_entry(
        session_id="session-1",
        turn_number=1,
        kind="user",
        content="hello",
        source="user",
    )
    backend = _FakeCorpusBackend()
    store._corpus_backend = backend
    now = utc_now_iso()
    store.conn.execute(
        """
        INSERT INTO publish_journal (
            target_name, object_kind, object_key, payload_json,
            status, attempt_count, last_error, created_at, updated_at
        ) VALUES (?, 'conversation_transcript', ?, '{}', ?, 1, 'timed out', ?, ?)
        """,
        (backend.target_name, f"transcript:{transcript_id}", status, now, now),
    )
    store.conn.commit()
    return store, backend


def _store_with_failed_transcript_journal(tmp_path):
    return _store_with_transcript_journal(tmp_path, status="failed")


def _store_with_pending_transcript_journal(tmp_path):
    return _store_with_transcript_journal(tmp_path, status="pending")


def test_add_transcript_entry_queues_semantic_publication_without_synchronous_backend_call(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("BRAINSTACK_SYNC_TRANSCRIPT_SEMANTIC_PUBLICATION", raising=False)
    store = BrainstackStore(
        str(tmp_path / "brainstack.db"),
        graph_backend="sqlite",
        corpus_backend="none",
    )
    store.open()
    backend = _FakeCorpusBackend()
    store._corpus_backend = backend
    try:
        transcript_id = store.add_transcript_entry(
            session_id="session-1",
            turn_number=1,
            kind="user",
            content="semantic publication should be queued, not blocking",
            source="user",
        )
        rows = store.list_publish_journal(target_name=backend.target_name, status="pending")
        assert backend.published == []
        assert [row["object_key"] for row in rows] == [f"transcript:{transcript_id}"]
    finally:
        store.close()


def test_failed_corpus_publications_are_not_replayed_on_open_path_by_default(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("BRAINSTACK_REPLAY_FAILED_PUBLICATIONS_ON_OPEN", raising=False)
    store, backend = _store_with_failed_transcript_journal(tmp_path)
    try:
        store._replay_corpus_publications_if_needed()
        assert backend.published == []
    finally:
        store.close()


def test_failed_corpus_publications_can_be_explicitly_replayed(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("BRAINSTACK_REPLAY_FAILED_PUBLICATIONS_ON_OPEN", "true")
    store, backend = _store_with_failed_transcript_journal(tmp_path)
    try:
        store._replay_corpus_publications_if_needed()
        assert len(backend.published) == 1
    finally:
        store.close()


def test_pending_conversation_transcripts_are_not_replayed_on_open_path_by_default(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("BRAINSTACK_REPLAY_CONVERSATION_TRANSCRIPTS_ON_OPEN", raising=False)
    store, backend = _store_with_pending_transcript_journal(tmp_path)
    try:
        store._replay_corpus_publications_if_needed()
        assert backend.published == []
    finally:
        store.close()


def test_pending_conversation_transcripts_can_be_explicitly_replayed(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("BRAINSTACK_REPLAY_CONVERSATION_TRANSCRIPTS_ON_OPEN", "true")
    store, backend = _store_with_pending_transcript_journal(tmp_path)
    try:
        store._replay_corpus_publications_if_needed()
        assert len(backend.published) == 1
    finally:
        store.close()
