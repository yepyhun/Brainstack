from __future__ import annotations

from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.file_corpus_source import FileCorpusSourceConfig, collect_file_corpus_sources, ingest_file_corpus_sources


PRINCIPAL_SCOPE = "principal:file-corpus-source"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _config(root: Path, **overrides: object) -> FileCorpusSourceConfig:
    params = {
        "source_root": root,
        "allow_patterns": ("**/*.md",),
        "source_adapter": "wiki",
        "doc_kind": "wiki_page",
        "principal_scope_key": PRINCIPAL_SCOPE,
        "max_file_bytes": 2_000,
        "max_sections": 4,
        "section_char_limit": 260,
    }
    params.update(overrides)
    return FileCorpusSourceConfig(**params)  # type: ignore[arg-type]


def test_file_corpus_source_enforces_allowlist_and_private_guards(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    _write(root / "pages" / "alpha.md", "# Alpha\n\nAlphaSourceAnchor belongs in corpus.")
    _write(root / "pages" / "magyar.md", "# Árvíztűrő\n\nMagyar wiki oldal többnyelvű corpus proof.")
    _write(root / ".hidden.md", "hidden content must not leak")
    _write(root / "auth-token.md", "token content must not leak")
    _write(root / "too-large.md", "x" * 3_000)
    (root / "binary.md").write_bytes(b"abc\x00def")
    outside = tmp_path / "outside.md"
    outside.write_text("outside secret", encoding="utf-8")
    (root / "outside-link.md").symlink_to(outside)

    collected = collect_file_corpus_sources(_config(root))

    source_ids = {source["source_id"] for source in collected["sources"]}
    assert source_ids == {"pages/alpha.md", "pages/magyar.md"}
    reasons = {row["reason"] for row in collected["skipped"]}
    assert {
        "dotfile_denied",
        "private_or_config_name_denied",
        "oversized_file_denied",
        "binary_file_denied",
        "symlink_traversal_denied",
    } <= reasons
    assert "token content must not leak" not in str(collected["skipped"])
    assert "outside secret" not in str(collected["skipped"])


def test_file_corpus_source_ingest_is_idempotent_and_updates_stale_pages(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    page = root / "alpha.md"
    _write(page, "# Alpha\n\nOldAlpha text.")
    store = _open_store(tmp_path)
    try:
        first = ingest_file_corpus_sources(store, _config(root))
        second = ingest_file_corpus_sources(store, _config(root))
        _write(page, "# Alpha\n\nNewAlpha text.")
        third = ingest_file_corpus_sources(store, _config(root))

        assert first["statuses"] == {"inserted": 1}
        assert second["statuses"] == {"unchanged": 1}
        assert third["statuses"] == {"updated": 1}
        assert store.search_corpus(query="OldAlpha", limit=3) == []
        assert store.search_corpus(query="NewAlpha", limit=3)
    finally:
        store.close()


def test_wiki_corpus_recall_is_bounded_cited_and_supporting_only(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    long_noise = "Noise paragraph. " * 120
    _write(root / "alpha.md", f"# Alpha\n\n{long_noise}\n\nNeedleWiki132 lives in this bounded corpus section.")
    _write(root / "unrelated.md", "# Unrelated\n\nThis page should not match the target query.")
    store = _open_store(tmp_path)
    try:
        receipt = ingest_file_corpus_sources(store, _config(root, section_char_limit=240, max_sections=8, max_file_bytes=8_000))
        assert receipt["source_count"] == 2

        report = build_query_inspect(
            store,
            query="NeedleWiki132 bounded corpus",
            session_id="wiki-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            corpus_limit=2,
            corpus_char_budget=300,
        )

        corpus = report["selected_evidence"]["corpus"]
        assert corpus
        assert corpus[0]["citation_id"].startswith("wiki:alpha.md#s")
        assert corpus[0]["corpus_taxonomy"]["source_uri_redacted"] is True
        assert corpus[0]["corpus_taxonomy"]["wing"] == "wiki_page"
        assert corpus[0]["corpus_taxonomy"]["mapping"] == "adapted_wing_room_drawer"
        assert corpus[0]["corpus_retrieval_trace"]["retrieval_mode"] == "bounded_hybrid_trace"
        assert "NeedleWiki132" in report["final_packet"]["preview"]
        assert long_noise[:200] not in report["final_packet"]["preview"]
        assert "unrelated.md" not in report["final_packet"]["preview"]
    finally:
        store.close()


def test_file_corpus_source_reports_section_cap_without_leaking_skipped_content(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    skipped_secret = "SkippedSectionSecretMustNotLeak"
    body = "\n\n".join([f"Section {index} text. " * 24 for index in range(5)] + [skipped_secret * 10])
    _write(root / "long.md", f"# Long\n\n{body}")

    collected = collect_file_corpus_sources(_config(root, max_sections=2, section_char_limit=30, max_file_bytes=8_000))

    assert collected["source_count"] == 1
    assert len(collected["sources"][0]["sections"]) == 2
    cap_rows = [row for row in collected["skipped"] if row["reason"] == "section_cap_exceeded"]
    assert cap_rows
    assert cap_rows[0]["skipped_section_count"] > 0
    assert skipped_secret not in str(collected["skipped"])
