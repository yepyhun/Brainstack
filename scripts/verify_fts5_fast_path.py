#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.db import BrainstackStore  # noqa: E402

SCHEMA = "brainstack.fts5_fast_path_verifier.v1"
REQUIRED_FTS_TABLES = {
    "profile_fts",
    "continuity_fts",
    "transcript_fts",
    "operating_fts",
    "corpus_section_fts",
}


def _table_count(store: BrainstackStore, table: str) -> int:
    row = store.conn.execute(f'SELECT COUNT(*) AS count FROM "{table}"').fetchone()
    return int(row["count"] if row is not None else 0)


def _fts_tables_present(store: BrainstackStore) -> dict[str, Any]:
    rows = store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    tables = {str(row["name"]) for row in rows}
    missing = sorted(REQUIRED_FTS_TABLES - tables)
    return {
        "status": "pass" if not missing else "fail",
        "missing": missing,
        "present": sorted(REQUIRED_FTS_TABLES & tables),
    }


def _first(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return rows[0] if rows else {}


def _row_pass(row: Mapping[str, Any], *, source: str, mode: str = "keyword") -> bool:
    return bool(row) and row.get("retrieval_source") == source and row.get("match_mode") == mode


def _seed(store: BrainstackStore, *, scope: str, session: str) -> None:
    store.upsert_profile_item(
        stable_key="identity:m008:fts5",
        category="identity",
        content="M008 profilekeyword german chinese continuity corpus lexical proof.",
        source="m008_fts5_verifier",
        confidence=0.99,
        metadata={"principal_scope_key": scope, "truth_eligible": True},
    )
    store.add_continuity_event(
        session_id=session,
        turn_number=1,
        kind="summary",
        content="M008 continuitykeyword public fast path evidence.",
        source="m008_fts5_verifier",
        metadata={"principal_scope_key": scope, "support_visibility": "support_only"},
    )
    store.add_transcript_entry(
        session_id=session,
        turn_number=2,
        kind="user",
        content="M008 transcriptkeyword public fast path evidence.",
        source="m008_fts5_verifier",
        metadata={"principal_scope_key": scope, "support_visibility": "support_only"},
    )
    store.upsert_operating_record(
        stable_key="operating:m008:fts5",
        principal_scope_key=scope,
        record_type="active_work",
        content="M008 operatingkeyword public fast path evidence.",
        owner="brainstack",
        source="m008_fts5_verifier",
        source_session_id=session,
        source_turn_number=3,
        metadata={"truth_eligible": True},
    )
    document_id = store.upsert_corpus_document(
        stable_key="doc:m008:fts5",
        title="M008 corpuskeyword lexical proof",
        doc_kind="public_fixture",
        source="m008_fts5_verifier",
        metadata={"principal_scope_key": scope, "truth_eligible": True},
    )
    store.replace_corpus_sections(
        document_id=document_id,
        title="M008 corpuskeyword lexical proof",
        sections=[
            {
                "heading": "Corpus fast path",
                "content": "M008 corpuskeyword public FTS5 section evidence.",
                "token_estimate": 12,
                "metadata": {"principal_scope_key": scope, "doc_type": "public_fixture", "language": "hu"},
            }
        ],
    )


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-m008-fts5-") as tmp:
        store = BrainstackStore(str(Path(tmp) / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        scope = "principal:m008:fts5"
        session = "session:m008:fts5"
        try:
            tables = _fts_tables_present(store)
            _seed(store, scope=scope, session=session)
            counts = {table: _table_count(store, table) for table in sorted(REQUIRED_FTS_TABLES)}
            profile = _first(store.search_profile(query="profilekeyword", limit=3, principal_scope_key=scope))
            continuity = _first(store.search_continuity(query="continuitykeyword", session_id=session, limit=3, principal_scope_key=scope))
            transcript = _first(store.search_transcript(query="transcriptkeyword", session_id=session, limit=3))
            transcript_global = _first(store.search_transcript_global(query="transcriptkeyword", session_id=session, limit=3, principal_scope_key=scope))
            operating = _first(store.search_operating_records(query="operatingkeyword", principal_scope_key=scope, limit=3))
            corpus = _first(store.search_corpus(query="corpuskeyword", limit=3))
        finally:
            store.close()

    cases = {
        "profile": {
            "status": "pass" if _row_pass(profile, source="profile.keyword") else "fail",
            "retrieval_source": profile.get("retrieval_source"),
            "match_mode": profile.get("match_mode"),
        },
        "continuity": {
            "status": "pass" if _row_pass(continuity, source="continuity.keyword") else "fail",
            "retrieval_source": continuity.get("retrieval_source"),
            "match_mode": continuity.get("match_mode"),
        },
        "transcript": {
            "status": "pass" if _row_pass(transcript, source="transcript.keyword") else "fail",
            "retrieval_source": transcript.get("retrieval_source"),
            "match_mode": transcript.get("match_mode"),
        },
        "transcript_global": {
            "status": "pass" if _row_pass(transcript_global, source="transcript.keyword") else "fail",
            "retrieval_source": transcript_global.get("retrieval_source"),
            "match_mode": transcript_global.get("match_mode"),
        },
        "operating": {
            "status": "pass" if _row_pass(operating, source="operating.keyword") else "fail",
            "retrieval_source": operating.get("retrieval_source"),
            "match_mode": operating.get("match_mode"),
        },
        "corpus": {
            "status": "pass" if _row_pass(corpus, source="corpus.keyword") else "fail",
            "retrieval_source": corpus.get("retrieval_source"),
            "match_mode": corpus.get("match_mode"),
        },
    }
    failures = [f"{name}:not_fts_keyword" for name, case in cases.items() if case["status"] != "pass"]
    if tables["status"] != "pass":
        failures.append("missing_fts_tables")
    for table, count in counts.items():
        if count <= 0:
            failures.append(f"{table}:empty_after_seed")
    report = {
        "schema": SCHEMA,
        "status": "pass" if not failures else "fail",
        "failure_reasons": failures,
        "fts_tables": tables,
        "fts_row_counts": counts,
        "cases": cases,
        "public_safe": True,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Brainstack FTS5 lexical fast-path coverage.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "failure_reasons": report["failure_reasons"]}, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
