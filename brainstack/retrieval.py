from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .db import BrainstackStore
from .provenance import summarize_provenance
from .temporal import record_is_effective_at


def _trim(value: str, max_len: int = 220) -> str:
    value = " ".join(value.split())
    if len(value) <= max_len:
        return value
    return value[: max_len - 3].rstrip() + "..."


def _render_items(items: Iterable[str]) -> str:
    rows = [item for item in items if item]
    return "\n".join(f"- {item}" for item in rows)


def _with_provenance(
    text: str,
    *,
    source: str = "",
    extra: str = "",
    provenance_mode: str = "compact",
    metadata: Dict[str, Any] | None = None,
) -> str:
    if provenance_mode != "expanded":
        return text
    parts = []
    if source:
        parts.append(f"source={source}")
    basis = summarize_provenance((metadata or {}).get("provenance"))
    if basis:
        parts.append(basis)
    if extra:
        parts.append(extra)
    if not parts:
        return text
    return f"{text} [{' ; '.join(parts)}]"


def _pack_corpus_rows(rows: Iterable[dict], *, char_budget: int, provenance_mode: str) -> List[str]:
    budget = max(180, int(char_budget))
    packed: List[str] = []
    seen = set()
    for row in rows:
        row_key = (row["document_id"], row["section_index"])
        if row_key in seen:
            continue
        seen.add(row_key)

        label = row["title"]
        heading = str(row.get("heading") or "").strip()
        if heading and heading != row["title"]:
            label = f"{label} > {heading}"

        remaining = budget - sum(len(item) for item in packed)
        snippet_cap = max(120, min(220, remaining - len(label) - 24))
        line = f"[{row['doc_kind']}] {label}: {_trim(row['content'], snippet_cap)}"
        line = _with_provenance(line, source=str(row.get("source", "")), provenance_mode=provenance_mode)
        if packed and remaining < len(line):
            break
        packed.append(line if len(line) <= remaining else _trim(line, remaining))
        if sum(len(item) for item in packed) >= budget:
            break
    return packed


def _pack_transcript_rows(rows: Iterable[dict], *, char_budget: int, provenance_mode: str) -> List[str]:
    budget = max(160, int(char_budget))
    packed: List[str] = []
    seen = set()
    for row in rows:
        row_key = (row["session_id"], row["id"])
        if row_key in seen:
            continue
        seen.add(row_key)

        remaining = budget - sum(len(item) for item in packed)
        if packed and remaining < 80:
            break

        label = f"[{row['kind']}] {_trim(row['content'], max_len=max(100, min(220, remaining - 24)))}"
        extra = ""
        if row.get("same_session"):
            extra = "same_session"
        line = _with_provenance(
            label,
            source=str(row.get("source", "")),
            extra=extra,
            provenance_mode=provenance_mode,
            metadata=row.get("metadata"),
        )
        packed.append(line if len(line) <= remaining else _trim(line, remaining))
        if sum(len(item) for item in packed) >= budget:
            break
    return packed


def build_system_prompt_block(store: BrainstackStore, *, profile_limit: int) -> str:
    items = store.list_profile_items(limit=profile_limit)
    if not items:
        return ""

    lines = []
    for item in items:
        label = item["category"].replace("_", " ")
        lines.append(f"[{label}] {_trim(item['content'], 140)}")

    return (
        "# Brainstack Profile\n"
        "Stable user and shared-work signals.\n"
        f"{_render_items(lines)}"
    )


def render_working_memory_block(
    *,
    policy: Dict[str, Any],
    profile_items: List[Dict[str, Any]],
    matched: List[Dict[str, Any]],
    recent: List[Dict[str, Any]],
    transcript_rows: List[Dict[str, Any]],
    graph_rows: List[Dict[str, Any]],
    corpus_rows: List[Dict[str, Any]],
) -> str:
    sections: List[str] = []
    provenance_mode = str(policy.get("provenance_mode", "compact"))

    if policy.get("show_policy"):
        lines = [
            f"[mode] {policy.get('mode', 'balanced')}",
            f"[confidence] {policy.get('confidence_band', 'medium')}",
            f"[provenance] {provenance_mode}",
            (
                "[tool-avoidance] allowed"
                if policy.get("tool_avoidance_allowed")
                else f"[tool-avoidance] disallowed: {policy.get('tool_avoidance_reason', '')}"
            ),
        ]
        if policy.get("conflict_escalation"):
            lines.append("[escalation] open conflict present; verification required")
        sections.append("## Brainstack Working Memory Policy\n" + _render_items(lines))

    if profile_items:
        lines = [
            _with_provenance(
                f"[{item['category'].replace('_', ' ')}] {_trim(item['content'], 160)}",
                source=str(item.get("source", "")),
                provenance_mode=provenance_mode,
                metadata=item.get("metadata"),
            )
            for item in profile_items
        ]
        sections.append("## Brainstack Profile Match\n" + _render_items(lines))

    if matched:
        lines = [
            _with_provenance(
                f"[{item['kind']}] {_trim(item['content'])}",
                source=str(item.get("source", "")),
                provenance_mode=provenance_mode,
                metadata=item.get("metadata"),
            )
            for item in matched
        ]
        sections.append("## Brainstack Continuity Match\n" + _render_items(lines))

    if recent:
        lines = [
            _with_provenance(
                f"[{item['kind']}] {_trim(item['content'])}",
                source=str(item.get("source", "")),
                provenance_mode=provenance_mode,
                metadata=item.get("metadata"),
            )
            for item in recent
        ]
        sections.append("## Brainstack Recent Continuity\n" + _render_items(lines))

    packed_transcript = _pack_transcript_rows(
        transcript_rows,
        char_budget=int(policy.get("transcript_char_budget", 320)),
        provenance_mode=provenance_mode,
    )
    if packed_transcript:
        sections.append("## Brainstack Transcript Evidence\n" + _render_items(packed_transcript))

    if graph_rows:
        show_graph_history = bool(policy.get("show_graph_history", False))
        conflicts = [row for row in graph_rows if row["row_type"] == "conflict"]
        current_states = [
            row for row in graph_rows if row["row_type"] == "state" and row.get("is_current") and record_is_effective_at(row)
        ]
        prior_states = [row for row in graph_rows if row["row_type"] == "state" and not row.get("is_current")]
        relations = [row for row in graph_rows if row["row_type"] == "relation"]
        ordered_rows = conflicts + current_states
        if show_graph_history or conflicts:
            ordered_rows.extend(prior_states)
        ordered_rows.extend(relations)

        lines = []
        seen = set()
        for row in ordered_rows:
            row_key = (
                row["row_type"],
                row.get("subject"),
                row.get("predicate"),
                row.get("object_value"),
                row.get("conflict_value"),
            )
            if row_key in seen:
                continue
            seen.add(row_key)
            if row["row_type"] == "relation":
                text = f"[relation] {row['subject']} {row['predicate']} {row['object_value']}"
                lines.append(
                    _with_provenance(
                        text,
                        source=str(row.get("source", "")),
                        provenance_mode=provenance_mode,
                        metadata=row.get("metadata"),
                    )
                )
            elif row["row_type"] == "conflict":
                text = (
                    f"[conflict] {row['subject']} {row['predicate']} "
                    f"current={row['object_value']} candidate={row['conflict_value']}"
                )
                conflict_basis = summarize_provenance((row.get("conflict_metadata") or {}).get("provenance"))
                extra = f"candidate_source={row.get('conflict_source', '')}"
                if conflict_basis:
                    extra = f"{extra} ; candidate_basis={conflict_basis}" if extra else f"candidate_basis={conflict_basis}"
                lines.append(
                    _with_provenance(
                        text,
                        source=str(row.get("source", "")),
                        extra=extra,
                        provenance_mode=provenance_mode,
                        metadata=row.get("metadata"),
                    )
                )
            else:
                current_marker = "current" if row.get("is_current") else "prior"
                text = f"[state:{current_marker}] {row['subject']} {row['predicate']}={row['object_value']}"
                lines.append(
                    _with_provenance(
                        text,
                        source=str(row.get("source", "")),
                        provenance_mode=provenance_mode,
                        metadata=row.get("metadata"),
                    )
                )
        sections.append("## Brainstack Graph Truth\n" + _render_items(lines))

    packed_corpus = _pack_corpus_rows(
        corpus_rows,
        char_budget=int(policy.get("corpus_char_budget", 360)),
        provenance_mode=provenance_mode,
    )
    if packed_corpus:
        sections.append("## Brainstack Corpus Recall\n" + _render_items(packed_corpus))

    return "\n\n".join(section for section in sections if section.strip())


def build_prefetch_block(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
    continuity_recent_limit: int,
    continuity_match_limit: int,
    profile_match_limit: int,
    transcript_match_limit: int,
    transcript_char_budget: int,
    graph_limit: int,
    corpus_limit: int,
    corpus_char_budget: int,
) -> str:
    profile_items = store.search_profile(query=query, limit=profile_match_limit)
    matched = store.search_continuity(query=query, session_id=session_id, limit=continuity_match_limit)
    matched_ids = {item["id"] for item in matched}
    recent = store.recent_continuity(session_id=session_id, limit=continuity_recent_limit)
    recent = [item for item in recent if item["id"] not in matched_ids]
    transcript_rows = store.search_transcript(query=query, session_id=session_id, limit=transcript_match_limit)
    graph_rows = store.search_graph(query=query, limit=graph_limit)
    corpus_rows = store.search_corpus(query=query, limit=max(corpus_limit * 3, corpus_limit))
    return render_working_memory_block(
        policy={
            "mode": "balanced",
            "collapse_mode": "balanced",
            "provenance_mode": "compact",
            "confidence_band": "medium",
            "conflict_escalation": False,
            "tool_avoidance_allowed": True,
            "tool_avoidance_reason": "legacy prefetch path",
            "show_policy": False,
            "show_graph_history": False,
            "transcript_char_budget": transcript_char_budget,
            "corpus_char_budget": corpus_char_budget,
        },
        profile_items=profile_items,
        matched=matched,
        recent=recent[:continuity_recent_limit],
        transcript_rows=transcript_rows[:transcript_match_limit],
        graph_rows=graph_rows,
        corpus_rows=corpus_rows,
    )


def build_compression_hint(snapshot: str) -> str:
    snapshot = _trim(snapshot, 500)
    if not snapshot:
        return ""
    return (
        "# Brainstack Continuity Preservation\n"
        "Preserve this continuity snapshot during compression.\n"
        f"- {snapshot}"
    )
