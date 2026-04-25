from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping


CORPUS_RETRIEVAL_TRACE_SCHEMA_VERSION = "brainstack.corpus_retrieval_trace.v1"
_TOKEN_RE = re.compile(r"\w{2,}", re.UNICODE)


def _tokens(value: Any) -> set[str]:
    return set(_TOKEN_RE.findall(str(value or "").casefold()))


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def annotate_corpus_retrieval_trace(
    rows: Iterable[Mapping[str, Any]],
    *,
    query: str,
    candidate_limit: int,
) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    query_tokens = _tokens(query)
    bounded_rows = [dict(row) for row in rows][: max(int(candidate_limit or 0), 0)]
    candidate_count = len(bounded_rows)
    for row in bounded_rows:
        content_tokens = _tokens(
            " ".join(
                str(row.get(key) or "")
                for key in ("title", "heading", "content", "doc_kind", "source", "citation_id")
            )
        )
        lexical_overlap = len(query_tokens & content_tokens)
        lexical_score = lexical_overlap / max(len(query_tokens), 1)
        semantic_score = _float(row.get("semantic_score"))
        keyword_score = _float(row.get("keyword_score"))
        source_signal = 1.0 if str(row.get("citation_id") or "").strip() else 0.0
        time_signal = 1.0 if str(row.get("created_at") or row.get("updated_at") or "").strip() else 0.0
        row["_brainstack_corpus_retrieval_trace"] = {
            "schema": CORPUS_RETRIEVAL_TRACE_SCHEMA_VERSION,
            "retrieval_mode": "bounded_hybrid_trace",
            "candidate_limit": max(int(candidate_limit or 0), 0),
            "candidate_count": candidate_count,
            "bounded": True,
            "semantic_score": semantic_score,
            "keyword_score": keyword_score,
            "lexical_overlap": lexical_overlap,
            "lexical_score": lexical_score,
            "source_signal": source_signal,
            "time_signal": time_signal,
            "explainable": bool(semantic_score > 0.0 or keyword_score > 0.0 or lexical_overlap > 0 or source_signal > 0.0),
        }
        output.append(row)
    return output
