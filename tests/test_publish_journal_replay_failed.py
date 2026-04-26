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


def _store_with_failed_transcript_journal(tmp_path):
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
        (backend.target_name, f"transcript:{transcript_id}", "failed", now, now),
    )
    store.conn.commit()
    return store, backend


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
