from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping

from .db import BrainstackStore
from .graph_lineage import compact_graph_source_lineage
from .literal_index import redact_literal_text
from .operating_context import render_operating_context_section
from .profile_contract import (
    is_native_explicit_style_item,
    normalize_profile_slot,
)
from .provenance import summarize_provenance
from .style_contract import STYLE_CONTRACT_SLOT
from .temporal import record_is_effective_at, record_temporal_status
from .transcript import primary_user_turn_content, trim_text_boundary


def _trim(value: str, max_len: int = 220) -> str:
    return trim_text_boundary(value, max_len=max_len)


def _render_user_first_exchange(content: Any, *, max_len: int) -> str:
    return _trim(primary_user_turn_content(content), max_len=max_len)


def _render_items(items: Iterable[str]) -> str:
    rows = [item for item in items if item]
    return "\n".join(f"- {item}" for item in rows)


def _render_numbered_items(items: Iterable[str]) -> str:
    rows = [item for item in items if item]
    return "\n".join(f"{index}. {item}" for index, item in enumerate(rows, start=1))


STYLE_AUTHORITY_RESIDUE_SLOTS = {
    STYLE_CONTRACT_SLOT,
}

_INTERNAL_CONTRACT_MARKERS = (
    "persona.md",
    "skill.md",
    "memory.md",
    "user.md",
    "/.hermes/",
    "~/.hermes/",
    "system prompt",
    "prompt block",
    "memory block",
    "loaded at startup",
    "loaded every reply",
    "every reply",
    "minden üzenetnél",
    "betöltődik",
    "betöltötte",
    "inject",
    "injected",
    "source_ai",
)

def _normalize_compare_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _is_native_profile_mirror_receipt(row: Dict[str, Any]) -> bool:
    return str(row.get("category") or "").strip() == "native_profile_mirror"


def _extract_identity_name_hint(value: Any) -> str:
    text = " ".join(str(value or "").strip().split())
    lowered = text.lower()
    if lowered.startswith("user's name is "):
        candidate = text[len("User's name is ") :].strip()
        if " (" in candidate:
            candidate = candidate.split(" (", 1)[0].strip()
        return _normalize_compare_text(candidate)
    return ""


def _row_metadata(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = row.get("metadata")
    return dict(payload) if isinstance(payload, dict) else {}


def _looks_like_internal_contract_text(value: Any) -> bool:
    normalized = _normalize_compare_text(value)
    if not normalized:
        return False
    return any(marker in normalized for marker in _INTERNAL_CONTRACT_MARKERS)


def _row_temporal_label(row: Dict[str, Any]) -> str:
    metadata = _row_metadata(row)
    temporal_payload = metadata.get("temporal")
    temporal = temporal_payload if isinstance(temporal_payload, dict) else {}
    raw = (
        str(temporal.get("observed_at") or "").strip()
        or str(row.get("created_at") or "").strip()
        or str(row.get("happened_at") or "").strip()
    )
    if not raw:
        return ""
    try:
        label = datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        label = raw.split("T", 1)[0] if "T" in raw else raw[:10]
    turn_number = int(row.get("turn_number") or 0)
    if turn_number > 0:
        return f"{label} | turn {turn_number}"
    return label


def _is_style_authority_residue_profile_item(row: Dict[str, Any]) -> bool:
    stable_key = normalize_profile_slot(str(row.get("stable_key") or "")).strip()
    return stable_key in STYLE_AUTHORITY_RESIDUE_SLOTS


def _has_native_explicit_style_generation(profile_items: Iterable[Dict[str, Any]]) -> bool:
    return any(is_native_explicit_style_item(row) for row in profile_items)


def _filter_compiled_behavior_profile_items(
    profile_items: Iterable[Dict[str, Any]],
    *,
    route_mode: str,
    preserve_style_contract: bool = False,
) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for row in profile_items:
        stable_key = str(row.get("stable_key") or "").strip()
        if route_mode != "style_contract" and not preserve_style_contract and stable_key == STYLE_CONTRACT_SLOT:
            continue
        output.append(row)
    return output


def _render_evidence_priority_section(title: str) -> str:
    preface = (
        "This private recalled memory context is background evidence, not new user input. "
        "Use explicit, committed, non-conflicted user/owner-backed records as authoritative. "
        "Supporting-only/runtime state is not active assignment or project-status truth. "
        "Pulse/scheduler evidence alone is not assignment truth. "
        "If asked about current work, assignment, or workstream and no explicit task/operating record is shown, say it is not recorded instead of inferring it from background evidence. "
        "Do not mention Brainstack blocks or memory internals unless asked."
    )
    return f"{title}\n{preface}"


def _extract_style_contract_profile_row(profile_items: Iterable[Dict[str, Any]]) -> Dict[str, Any] | None:
    for row in profile_items:
        if str(row.get("stable_key") or "").strip() == STYLE_CONTRACT_SLOT:
            return row
    return None


def _render_exact_contract_section(
    title: str,
    row: Mapping[str, Any] | None,
    *,
    char_budget: int,
    provenance_mode: str,
) -> str:
    if not isinstance(row, Mapping):
        return ""
    content = _trim(redact_literal_text(str(row.get("content") or "")), max_len=max(320, int(char_budget)))
    if not content:
        return ""
    preface = (
        "This is the canonical archival rule pack recalled for explicit lookup or debugging. "
        "Use it as exact stored truth."
    )
    line = _with_provenance(
        content,
        source=str(row.get("source") or ""),
        provenance_mode=provenance_mode,
        metadata=row.get("metadata"),
    )
    return f"{title}\n{preface}\n{line}"


def _render_truthful_memory_operations_section(title: str) -> str:
    lines = [
        "Claim a durable Brainstack save only when the current turn includes a committed write receipt or a successful memory-tool result.",
        "If a domain has no structured owner in this runtime, say that explicitly instead of implying a committed record exists.",
        "Claim that a reminder, cron job, or scheduled follow-up exists only when the current evidence includes a native scheduler record or a successful scheduler/tool result from this run.",
        "A memory entry, task note, continuity summary, transcript line, or internal task list is not by itself a scheduled job.",
        "For task and commitment lookups, committed Brainstack task records are authoritative when present; continuity or transcript recall is supporting evidence only after a structured miss.",
        "For operating-truth lookups, committed Brainstack operating records are authoritative when present; continuity summaries are fallback only when that owner has no committed record.",
    ]
    return f"{title}\n{_render_items(lines)}"


def build_system_prompt_projection(
    store: BrainstackStore,
    *,
    profile_limit: int,
    principal_scope_key: str = "",
    session_id: str = "",
    include_behavior_contract: bool = True,
) -> Dict[str, Any]:
    fetch_limit = max(profile_limit * 3, 10)
    items = store.list_profile_items(limit=fetch_limit, principal_scope_key=principal_scope_key)
    behavior_snapshot = store.get_behavior_policy_snapshot(principal_scope_key=principal_scope_key)
    canonical_style_present = bool(
        isinstance(behavior_snapshot, Mapping)
        and isinstance(behavior_snapshot.get("raw_contract"), Mapping)
        and bool(behavior_snapshot.get("raw_contract", {}).get("present"))
    )
    native_explicit_style_present = _has_native_explicit_style_generation(items)
    operating_context_snapshot = store.get_operating_context_snapshot(
        principal_scope_key=principal_scope_key,
        session_id=session_id,
    )
    hidden_profile_keys: set[str] = set()
    filtered_items = list(items)

    filtered_items = [item for item in filtered_items if not _is_native_profile_mirror_receipt(item)]

    if canonical_style_present or native_explicit_style_present:
        filtered_items = [item for item in filtered_items if not _is_style_authority_residue_profile_item(item)]

    operating_context_section = render_operating_context_section(operating_context_snapshot)
    truthful_memory_operations_section = _render_truthful_memory_operations_section(
        "# Brainstack Truthful Memory Operations"
    )
    operating_context_profile_keys = {
        str(entry.get("stable_key") or "").strip()
        for entry in list(operating_context_snapshot.get("stable_profile_entries") or [])
        if isinstance(entry, Mapping) and str(entry.get("stable_key") or "").strip()
    }
    rendered_profile_keys: List[str] = []
    profile_lines: List[str] = []
    for item in filtered_items[:profile_limit]:
        stable_key = str(item.get("stable_key") or "").strip()
        if stable_key and stable_key in operating_context_profile_keys:
            continue
        if stable_key:
            rendered_profile_keys.append(stable_key)
        label = item["category"].replace("_", " ")
        profile_lines.append(f"[{label}] {_trim(item['content'], 140)}")

    sections: List[str] = []
    if operating_context_section:
        sections.append(operating_context_section)
    if operating_context_section or profile_lines:
        sections.append(truthful_memory_operations_section)
    if profile_lines:
        sections.append(
            "# Brainstack Profile\n"
            "Stable user and shared-work signals.\n"
            f"{_render_items(profile_lines)}"
        )

    return {
        "block": "\n\n".join(section for section in sections if section.strip()),
        "contract_present": False,
        "native_preferences_present": False,
        "operating_context_present": bool(operating_context_section),
        "truthful_memory_operations_present": bool(
            operating_context_section or profile_lines
        ),
        "rendered_profile_keys": tuple(rendered_profile_keys),
        "hidden_profile_keys": tuple(sorted(hidden_profile_keys)),
        "canonical_style_present": canonical_style_present,
        "native_explicit_style_present": native_explicit_style_present,
        "active_lane_source_revision": 0,
    }


def _render_lookup_semantics_section(payload: Mapping[str, Any] | None) -> str:
    if not isinstance(payload, Mapping):
        return ""
    if not bool(payload.get("active")):
        return ""
    lines: List[str] = []
    domain = str(payload.get("domain") or "").strip()
    if domain == "operating_truth":
        record_types = [
            str(value or "").strip().replace("_", " ")
            for value in (payload.get("record_types") or ())
            if str(value or "").strip()
        ]
        if str(payload.get("structured_owner_status") or "").strip() == "brainstack.operating_truth":
            lines.append("Brainstack operating truth is the structured owner for this lookup in this runtime.")
        if record_types:
            lines.append("Requested operating records: " + ", ".join(record_types) + ".")
        result_status = str(payload.get("result_status") or "").strip()
        if result_status == "committed_records":
            lines.append(
                f"Use the committed Brainstack operating records below as authoritative ({int(payload.get('authoritative_record_count') or payload.get('structured_record_count') or 0)} record(s))."
            )
        elif result_status == "supporting_records_only":
            lines.append(
                "Only supporting Brainstack runtime/operating evidence matched this lookup; do not treat it as active assignment or project-status truth."
            )
        else:
            lines.append("No committed Brainstack operating record matched this lookup.")
    elif domain == "recent_work_recap":
        record_types = [
            str(value or "").strip().replace("_", " ")
            for value in (payload.get("record_types") or ())
            if str(value or "").strip()
        ]
        if str(payload.get("structured_owner_status") or "").strip() == "brainstack.operating_truth":
            lines.append("Brainstack operating truth is carrying the restart-surviving recent-work summary in this runtime.")
        if record_types:
            lines.append("Recent-work record types present: " + ", ".join(record_types) + ".")
        lines.append(
            f"Use the committed Brainstack recent-work records below as the primary recap substrate ({int(payload.get('structured_record_count') or 0)} record(s))."
        )
        fallback_sources = list(payload.get("fallback_sources") or [])
        if fallback_sources:
            lines.append("Supporting shelves also contributed: " + ", ".join(str(source) for source in fallback_sources) + ".")
    elif domain == "task_like":
        owner_status = str(payload.get("structured_owner_status") or "").strip()
        result_status = str(payload.get("result_status") or "").strip()
        fallback_sources = list(payload.get("fallback_sources") or [])
        structured_record_count = int(payload.get("structured_record_count") or 0)
        due_date = str(payload.get("due_date") or "").strip()
        if owner_status == "brainstack.task_memory":
            lines.append("Brainstack task memory is the structured owner for this lookup in this runtime.")
            if due_date:
                lines.append(f"Structured lookup due date: {due_date}.")
        elif owner_status == "absent":
            lines.append("No structured task owner is attached to Brainstack in this runtime.")
        if result_status == "committed_records":
            lines.append(
                f"Use the committed Brainstack task records below as authoritative for this date scope ({structured_record_count} record(s))."
            )
        elif result_status == "structured_miss_with_fallback":
            lines.append(
                "No committed Brainstack task record matched this lookup. Any task-like lines recalled below are continuity evidence only."
            )
        elif result_status == "structured_miss":
            lines.append(
                "No committed Brainstack task record matched this lookup, and no supporting continuity or transcript evidence was recalled."
            )
        if fallback_sources:
            prefix = (
                "Lookup also considered supporting shelves: "
                if result_status == "committed_records"
                else "Lookup path used supporting shelves only: "
            )
            lines.append(prefix + ", ".join(str(source) for source in fallback_sources) + ".")
    return f"## Brainstack Lookup Semantics\n{_render_items(lines)}" if lines else ""


def _render_task_memory_section(
    rows: Iterable[Dict[str, Any]],
    *,
    provenance_mode: str,
) -> str:
    task_lines: List[str] = []
    for row in rows:
        title = redact_literal_text(" ".join(str(row.get("title") or "").strip().split()))
        if not title:
            continue
        prefix = "optional" if bool(row.get("optional")) else "open"
        due_date = str(row.get("due_date") or "").strip()
        text = f"[{prefix}] {title}"
        extra = f"due_date={due_date}" if due_date else ""
        task_lines.append(
            _with_provenance(
                text,
                source=str(row.get("source") or ""),
                extra=extra,
                provenance_mode=provenance_mode,
                metadata=row.get("metadata"),
            )
        )
    if not task_lines:
        return ""
    return "## Brainstack Task Memory\n" + _render_items(task_lines)


def _render_operating_truth_section(
    rows: Iterable[Dict[str, Any]],
    *,
    provenance_mode: str,
) -> str:
    operating_lines: List[str] = []
    for row in rows:
        content = redact_literal_text(_normalize_compare_text(row.get("content")))
        if not content:
            continue
        record_type = str(row.get("record_type") or "operating_truth").strip()
        if record_type == "live_system_state":
            label = "supporting runtime state (not assigned work)"
            content = f"{content} [supporting only; not active workstream/project status]"
        else:
            label = record_type.replace("_", " ")
        operating_lines.append(
            _with_provenance(
                f"[{label}] {content}",
                source=str(row.get("source") or ""),
                provenance_mode=provenance_mode,
                metadata=row.get("metadata"),
            )
        )
    if not operating_lines:
        return ""
    return "## Brainstack Operating Truth\n" + _render_items(operating_lines)


def _graph_fact_class(row: Dict[str, Any]) -> str:
    value = str(row.get("fact_class") or "").strip()
    if value:
        return value
    row_type = str(row.get("row_type") or "").strip()
    if row_type == "conflict":
        return "conflict"
    if row_type == "inferred_relation":
        return "inferred_relation"
    if row_type == "relation":
        return "explicit_relation"
    if row_type == "state":
        temporal_status = record_temporal_status(row)
        if row.get("is_current") and temporal_status == "current" and record_is_effective_at(row):
            return "explicit_state_current"
        if row.get("is_current") and temporal_status == "expired":
            return "explicit_state_expired"
        return "explicit_state_prior"
    return row_type or "graph"


def _render_graph_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    provenance_mode: str,
) -> List[str]:
    lines: List[str] = []
    seen = set()
    for row in rows:
        row_key = (
            row.get("row_type"),
            row.get("subject"),
            row.get("predicate"),
            row.get("object_value"),
            row.get("conflict_value"),
            row.get("fact_class"),
        )
        if row_key in seen:
            continue
        seen.add(row_key)
        fact_class = _graph_fact_class(row)
        graph_extra = _graph_provenance_note(row)
        if fact_class == "explicit_relation":
            text = _append_compact_note(
                f"[relation:explicit] {row['subject']} {row['predicate']} {row['object_value']}",
                graph_extra,
            )
            lines.append(
                _with_provenance(
                    text,
                    source=str(row.get("source", "")),
                    extra=graph_extra,
                    provenance_mode=provenance_mode,
                    metadata=row.get("metadata"),
                )
            )
            continue
        if fact_class == "inferred_relation":
            reason = str((row.get("metadata") or {}).get("inference_reason") or "").strip()
            extra = f"reason={reason}" if reason else ""
            extra = _join_note_parts(extra, graph_extra)
            text = _append_compact_note(
                f"[relation:inferred] {row['subject']} {row['predicate']} {row['object_value']}",
                graph_extra,
            )
            lines.append(
                _with_provenance(
                    text,
                    source=str(row.get("source", "")),
                    extra=extra,
                    provenance_mode=provenance_mode,
                    metadata=row.get("metadata"),
                )
            )
            continue
        if fact_class == "conflict":
            text = _append_compact_note(
                (
                    f"[conflict] {row['subject']} {row['predicate']} "
                    f"current={row['object_value']} candidate={row['conflict_value']}"
                ),
                _graph_provenance_note(row, conflict=True),
            )
            conflict_basis = summarize_provenance((row.get("conflict_metadata") or {}).get("provenance"))
            extra = f"candidate_source={row.get('conflict_source', '')}"
            if conflict_basis:
                extra = f"{extra} ; candidate_basis={conflict_basis}" if extra else f"candidate_basis={conflict_basis}"
            extra = _join_note_parts(extra, _graph_provenance_note(row, conflict=True))
            lines.append(
                _with_provenance(
                    text,
                    source=str(row.get("source", "")),
                    extra=extra,
                    provenance_mode=provenance_mode,
                    metadata=row.get("metadata"),
                )
            )
            continue
        current_marker = "current" if fact_class == "explicit_state_current" else "expired" if fact_class == "explicit_state_expired" else "prior"
        text = _append_compact_note(
            f"[state:{current_marker}] {row['subject']} {row['predicate']}={row['object_value']}",
            graph_extra,
        )
        lines.append(
            _with_provenance(
                text,
                source=str(row.get("source", "")),
                extra=graph_extra,
                provenance_mode=provenance_mode,
                metadata=row.get("metadata"),
            )
        )
    return lines


def _join_note_parts(*parts: str) -> str:
    return " ; ".join(part for part in parts if str(part or "").strip())


def _append_compact_note(text: str, note: str) -> str:
    return f"{text} [{note}]" if note else text


def _graph_provenance_note(row: Mapping[str, Any], *, conflict: bool = False) -> str:
    metadata = row.get("conflict_metadata") if conflict else row.get("metadata")
    lineage = compact_graph_source_lineage(metadata if isinstance(metadata, Mapping) else {})
    if not lineage:
        return "lineage=missing"
    source_kind = str(lineage.get("source_kind") or "").strip()
    source_stable_id = str(lineage.get("source_stable_id") or "").strip()
    status = str(lineage.get("status") or "").strip()
    provenance_class = str(lineage.get("provenance_class") or "").strip()
    parts = []
    if source_kind or source_stable_id:
        parts.append(f"src={source_kind}:{source_stable_id}".rstrip(":"))
    if provenance_class:
        parts.append(f"prov={provenance_class}")
    if status and status != "active":
        parts.append(f"lineage={status}")
    return " ; ".join(parts)


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
    seen_snippets = set()
    per_document_count: Dict[int, int] = {}
    for row in rows:
        row_key = (row["document_id"], row["section_index"])
        if row_key in seen:
            continue
        seen.add(row_key)
        document_id = int(row.get("document_id") or 0)
        if per_document_count.get(document_id, 0) >= 2:
            continue

        label = row["title"]
        heading = str(row.get("heading") or "").strip()
        if heading and heading != row["title"]:
            label = f"{label} > {heading}"
        citation_id = str(row.get("citation_id") or "").strip()
        if citation_id:
            label = f"{label} [{citation_id}]"
        content = str(row.get("content") or "").strip()
        snippet_fingerprint = _normalize_compare_text(" ".join(content.split())[:220])
        if snippet_fingerprint and snippet_fingerprint in seen_snippets:
            continue

        remaining = budget - sum(len(item) for item in packed)
        snippet_cap = max(140, min(360, remaining - len(label) - 24))
        line = f"[{row['doc_kind']}] {label}: {_trim(redact_literal_text(content), snippet_cap)}"
        line = _with_provenance(line, source=str(row.get("source", "")), provenance_mode=provenance_mode)
        if packed and remaining < len(line):
            break
        packed.append(line if len(line) <= remaining else _trim(line, remaining))
        if snippet_fingerprint:
            seen_snippets.add(snippet_fingerprint)
        per_document_count[document_id] = per_document_count.get(document_id, 0) + 1
        if sum(len(item) for item in packed) >= budget:
            break
    return packed


def _pack_continuity_rows(rows: Iterable[dict], *, char_budget: int, provenance_mode: str) -> List[str]:
    budget = max(220, int(char_budget))
    packed: List[str] = []
    seen = set()
    unique_rows: List[dict] = []
    for row in rows:
        row_key = (str(row.get("session_id") or ""), int(row.get("id") or 0))
        if row_key in seen:
            continue
        seen.add(row_key)
        unique_rows.append(row)

    for index, row in enumerate(unique_rows):
        remaining = budget - sum(len(item) for item in packed)
        if packed and remaining < 120:
            break

        temporal_label = _row_temporal_label(row)
        evidence_label = str(row.get("kind") or "turn")
        prefix = f"[{temporal_label} | {evidence_label}]" if temporal_label else f"[{evidence_label}]"
        remaining_items = max(1, len(unique_rows) - index)
        per_row_budget = max(140, remaining // remaining_items)
        snippet_cap = max(140, min(280, per_row_budget - len(prefix) - 24))
        line = f"{prefix} {_render_user_first_exchange(redact_literal_text(row.get('content') or ''), max_len=snippet_cap)}"
        line = _with_provenance(
            line,
            source=str(row.get("source", "")),
            provenance_mode=provenance_mode,
            metadata=row.get("metadata"),
        )
        packed.append(line if len(line) <= remaining else _trim(line, remaining))
        if sum(len(item) for item in packed) >= budget:
            break
    return packed


def _pack_transcript_rows(rows: Iterable[dict], *, char_budget: int, provenance_mode: str) -> List[str]:
    budget = max(240, int(char_budget))
    packed: List[str] = []
    seen = set()
    unique_rows: List[dict] = []
    for row in rows:
        row_key = (row["session_id"], row["id"])
        if row_key in seen:
            continue
        seen.add(row_key)
        unique_rows.append(row)

    for index, row in enumerate(unique_rows):
        remaining = budget - sum(len(item) for item in packed)
        if packed and remaining < 120:
            break

        temporal_label = _row_temporal_label(row)
        evidence_label = str(row.get("kind") or "turn")
        prefix = f"[{temporal_label} | {evidence_label}]" if temporal_label else f"[{evidence_label}]"
        remaining_items = max(1, len(unique_rows) - index)
        per_row_budget = max(160, remaining // remaining_items)
        snippet_cap = max(160, min(320, per_row_budget - len(prefix) - 24))
        label = f"{prefix} {_render_user_first_exchange(redact_literal_text(row.get('content') or ''), max_len=snippet_cap)}"
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


def _pack_aggregate_rows(rows: Iterable[dict], *, char_budget: int, provenance_mode: str) -> List[str]:
    budget = max(420, int(char_budget))
    packed: List[str] = []
    seen = set()
    for row in rows:
        row_key = (
            str(row.get("session_id") or ""),
            int(row.get("id") or 0),
            str(row.get("kind") or row.get("row_type") or ""),
            _normalize_compare_text(row.get("content") or ""),
        )
        if row_key in seen:
            continue
        seen.add(row_key)

        remaining = budget - sum(len(item) for item in packed)
        if packed and remaining < 120:
            break

        temporal_label = _row_temporal_label(row)
        evidence_label = str(row.get("kind") or row.get("row_type") or "item")
        prefix = f"[{temporal_label} | {evidence_label}]" if temporal_label else f"[{evidence_label}]"
        content = redact_literal_text(str(row.get("content") or ""))
        snippet_cap = max(180, min(360, remaining - len(prefix) - 24))
        lowered = content.lower()
        if "user:" in lowered and "assistant:" in lowered:
            body = _render_user_first_exchange(content, max_len=snippet_cap)
        else:
            body = _trim(content, max_len=snippet_cap)
        line = f"{prefix} {body}"
        extra = "same_session" if row.get("same_session") else ""
        line = _with_provenance(
            line,
            source=str(row.get("source", "")),
            extra=extra,
            provenance_mode=provenance_mode,
            metadata=row.get("metadata"),
        )
        packed.append(line if len(line) <= remaining else _trim(line, remaining))
        if sum(len(item) for item in packed) >= budget:
            break
    return packed


def build_system_prompt_block(
    store: BrainstackStore,
    *,
    profile_limit: int,
    principal_scope_key: str = "",
    session_id: str = "",
    include_behavior_contract: bool = True,
) -> str:
    return str(
        build_system_prompt_projection(
            store,
            profile_limit=profile_limit,
            principal_scope_key=principal_scope_key,
            session_id=session_id,
            include_behavior_contract=include_behavior_contract,
        ).get("block")
        or ""
    )


def _row_overlap_markers(row: Mapping[str, Any], *, transcript_like: bool = False) -> set[tuple[str, str]]:
    markers: set[tuple[str, str]] = set()
    session_id = str(row.get("session_id") or "").strip()
    row_id = int(row.get("id") or 0)
    if session_id and row_id > 0:
        markers.add(("row", f"{session_id}:{row_id}"))
    turn_number = int(row.get("turn_number") or 0)
    if session_id and turn_number > 0:
        markers.add(("turn", f"{session_id}:{turn_number}"))
    content = redact_literal_text(str(row.get("content") or "").strip())
    if content:
        rendered = (
            _render_user_first_exchange(content, max_len=220)
            if transcript_like or ("user:" in content.lower() and "assistant:" in content.lower())
            else _trim(content, 220)
        )
        fingerprint = _normalize_compare_text(rendered)
        if fingerprint:
            markers.add(("fp", fingerprint))
    return markers


def _suppress_overlapping_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    seen_markers: set[tuple[str, str]] | None = None,
    transcript_like: bool = False,
) -> List[Dict[str, Any]]:
    consumed = set(seen_markers or set())
    kept: List[Dict[str, Any]] = []
    for raw_row in rows:
        row = dict(raw_row)
        markers = _row_overlap_markers(row, transcript_like=transcript_like)
        if markers and markers & consumed:
            continue
        kept.append(row)
        consumed.update(markers)
    return kept


def _style_contract_render_state(
    *,
    policy: Mapping[str, Any],
    route_mode: str,
    profile_items: List[Dict[str, Any]],
    provenance_mode: str,
) -> tuple[str, set[str], bool, bool]:
    behavior_snapshot = policy.get("behavior_policy_snapshot") if isinstance(policy, dict) else None
    canonical_style_present = bool(
        isinstance(behavior_snapshot, Mapping)
        and isinstance(behavior_snapshot.get("raw_contract"), Mapping)
        and bool(behavior_snapshot.get("raw_contract", {}).get("present"))
    )
    exact_contract_section = ""
    hidden_profile_keys: set[str] = set()
    style_contract_row = _extract_style_contract_profile_row(profile_items)
    native_explicit_style_present = _has_native_explicit_style_generation(profile_items)
    if route_mode != "style_contract":
        return exact_contract_section, hidden_profile_keys, canonical_style_present, native_explicit_style_present

    exact_contract_section = _render_exact_contract_section(
        "## Brainstack Canonical Rule Pack",
        style_contract_row,
        char_budget=max(480, int(policy.get("style_contract_char_budget", 2400))),
        provenance_mode=provenance_mode,
    )
    if exact_contract_section or not native_explicit_style_present:
        return exact_contract_section, hidden_profile_keys, canonical_style_present, native_explicit_style_present

    for row in profile_items:
        if not is_native_explicit_style_item(row):
            continue
        hidden_profile_keys.add(str(row.get("stable_key") or "").strip())
        exact_contract_section = _render_exact_contract_section(
            "## Brainstack Mirrored Native Rule Pack",
            row,
            char_budget=max(480, int(policy.get("style_contract_char_budget", 2400))),
            provenance_mode=provenance_mode,
        )
        if exact_contract_section:
            break
    return exact_contract_section, hidden_profile_keys, canonical_style_present, native_explicit_style_present


def _render_working_memory_policy_section(policy: Mapping[str, Any], *, provenance_mode: str) -> str:
    if not policy.get("show_policy"):
        return ""
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
    return "## Brainstack Working Memory Policy\n" + _render_items(lines)


def _render_continuation_guidance_section(policy: Mapping[str, Any]) -> str:
    if not policy.get("continuation_emphasis"):
        return ""
    return (
        "## Brainstack Continuation Guidance\n"
        + _render_items(
            [
                "The user is resuming an existing thread. Carry forward still-relevant concrete details, constraints, named participants, venues, and unresolved tasks from the recalled evidence below.",
                "Do not invent missing details or add constraints that are not grounded in the recalled evidence.",
            ]
        )
    )


def _filtered_profile_items_for_packet(
    profile_items: List[Dict[str, Any]],
    *,
    route_mode: str,
    hidden_profile_keys: set[str],
    substrate_profile_keys: set[str],
    canonical_style_present: bool,
    native_explicit_style_present: bool,
    exact_contract_section: str,
    compiled_policy_active: bool,
) -> List[Dict[str, Any]]:
    if compiled_policy_active:
        filtered_profile_items = _filter_compiled_behavior_profile_items(profile_items, route_mode=route_mode)
    else:
        filtered_profile_items = [
            item
            for item in profile_items
            if str(item.get("stable_key") or "").strip() not in hidden_profile_keys
            and str(item.get("stable_key") or "").strip() not in substrate_profile_keys
        ]
        if route_mode != "style_contract":
            filtered_profile_items = [
                item for item in filtered_profile_items if str(item.get("stable_key") or "").strip() != STYLE_CONTRACT_SLOT
            ]
    if canonical_style_present or native_explicit_style_present or exact_contract_section:
        filtered_profile_items = [item for item in filtered_profile_items if not _is_style_authority_residue_profile_item(item)]
    if exact_contract_section:
        filtered_profile_items = [
            item for item in filtered_profile_items if str(item.get("stable_key") or "").strip() != STYLE_CONTRACT_SLOT
        ]
    return [item for item in filtered_profile_items if not _is_native_profile_mirror_receipt(item)]


def _render_profile_match_section(
    profile_items: List[Dict[str, Any]],
    *,
    policy: Mapping[str, Any],
    route_mode: str,
    provenance_mode: str,
) -> str:
    if not profile_items:
        return ""
    style_contract_char_budget = max(320, int(policy.get("style_contract_char_budget", 2400)))
    lines = []
    for item in profile_items:
        content = redact_literal_text(str(item.get("content") or ""))
        stable_key = str(item.get("stable_key") or "").strip()
        rendered_content = (
            _trim(content, style_contract_char_budget)
            if stable_key == STYLE_CONTRACT_SLOT
            and (route_mode == "style_contract" or bool(policy.get("show_authoritative_contract")))
            else _trim(content, 160)
        )
        lines.append(
            _with_provenance(
                f"[{item['category'].replace('_', ' ')}] {rendered_content}",
                source=str(item.get("source", "")),
                provenance_mode=provenance_mode,
                metadata=item.get("metadata"),
            )
        )
    return "## Brainstack Profile Match\n" + _render_items(lines)


def _render_continuity_or_aggregate_sections(
    *,
    route_mode: str,
    matched: List[Dict[str, Any]],
    recent: List[Dict[str, Any]],
    transcript_rows: List[Dict[str, Any]],
    policy: Mapping[str, Any],
    provenance_mode: str,
) -> List[str]:
    if route_mode == "aggregate":
        packed_aggregate = _pack_aggregate_rows(
            [*matched, *recent, *transcript_rows],
            char_budget=max(960, int(policy.get("transcript_char_budget", 320))),
            provenance_mode=provenance_mode,
        )
        if not packed_aggregate:
            return []
        return [
            "## Brainstack Aggregate Evidence\n"
            "Each numbered line below is a separate recalled item. Combine only the items that actually match the user question.\n"
            + _render_numbered_items(packed_aggregate)
        ]

    deduped_matched = _suppress_overlapping_rows(matched)
    deduped_recent = _suppress_overlapping_rows(
        recent,
        seen_markers={marker for row in deduped_matched for marker in _row_overlap_markers(row)},
    )
    deduped_transcript = _suppress_overlapping_rows(
        transcript_rows,
        seen_markers={marker for row in [*deduped_matched, *deduped_recent] for marker in _row_overlap_markers(row)},
        transcript_like=True,
    )
    if not deduped_transcript and transcript_rows:
        deduped_transcript = [dict(transcript_rows[0])]

    sections: List[str] = []
    if deduped_matched:
        lines = _pack_continuity_rows(
            deduped_matched,
            char_budget=max(320, min(900, 260 * max(1, len(deduped_matched)))),
            provenance_mode=provenance_mode,
        )
        sections.append("## Brainstack Continuity Match\n" + _render_items(lines))
    if deduped_recent:
        lines = _pack_continuity_rows(
            deduped_recent,
            char_budget=max(240, min(640, 220 * max(1, len(deduped_recent)))),
            provenance_mode=provenance_mode,
        )
        sections.append("## Brainstack Recent Continuity\n" + _render_items(lines))
    packed_transcript = _pack_transcript_rows(
        deduped_transcript,
        char_budget=int(policy.get("transcript_char_budget", 320)),
        provenance_mode=provenance_mode,
    )
    if packed_transcript:
        sections.append("## Brainstack Transcript Evidence\n" + _render_items(packed_transcript))
    return sections


def _render_graph_truth_section(
    graph_rows: List[Dict[str, Any]],
    *,
    policy: Mapping[str, Any],
    provenance_mode: str,
) -> str:
    if not graph_rows:
        return ""
    show_graph_history = bool(policy.get("show_graph_history", False))
    current_truth = [
        row for row in graph_rows if _graph_fact_class(row) in {"explicit_state_current", "explicit_relation"}
    ]
    conflicts = [row for row in graph_rows if _graph_fact_class(row) == "conflict"]
    historical_truth = [
        row for row in graph_rows if _graph_fact_class(row) in {"explicit_state_prior", "explicit_state_expired"}
    ]
    inferred_links = [
        row for row in graph_rows if _graph_fact_class(row) == "inferred_relation"
    ][: max(0, int(policy.get("graph_inferred_limit", 2)))]

    graph_sections: List[str] = []
    current_lines = _render_graph_rows(current_truth, provenance_mode=provenance_mode)
    if current_lines:
        graph_sections.append("### Current Truth\n" + _render_items(current_lines))
    conflict_lines = _render_graph_rows(conflicts, provenance_mode=provenance_mode)
    if conflict_lines:
        graph_sections.append("### Open Conflicts\n" + _render_items(conflict_lines))
    if show_graph_history or conflicts or any(_graph_fact_class(row) == "explicit_state_expired" for row in historical_truth):
        history_lines = _render_graph_rows(historical_truth, provenance_mode=provenance_mode)
        if history_lines:
            graph_sections.append("### Historical Truth\n" + _render_items(history_lines))
    inferred_lines = _render_graph_rows(inferred_links, provenance_mode=provenance_mode)
    if inferred_lines:
        graph_sections.append("### Inferred Links\n" + _render_items(inferred_lines))
    if not graph_sections:
        return ""
    return "## Brainstack Graph Truth\n" + "\n\n".join(graph_sections)


def render_working_memory_block(
    *,
    policy: Dict[str, Any],
    route_mode: str = "fact",
    profile_items: List[Dict[str, Any]],
    task_rows: List[Dict[str, Any]],
    matched: List[Dict[str, Any]],
    recent: List[Dict[str, Any]],
    transcript_rows: List[Dict[str, Any]],
    graph_rows: List[Dict[str, Any]],
    corpus_rows: List[Dict[str, Any]],
    operating_rows: List[Dict[str, Any]] | None = None,
    system_substrate: Mapping[str, Any] | None = None,
) -> str:
    sections: List[str] = []
    provenance_mode = str(policy.get("provenance_mode", "compact"))
    compiled_policy_active = False
    system_substrate = system_substrate if isinstance(system_substrate, Mapping) else {}
    suppress_evidence_priority = bool(system_substrate.get("truthful_memory_operations_present"))
    substrate_profile_keys = {
        str(key).strip() for key in (system_substrate.get("rendered_profile_keys") or ()) if str(key).strip()
    }
    exact_contract_section, hidden_profile_keys, canonical_style_present, native_explicit_style_present = (
        _style_contract_render_state(
            policy=policy,
            route_mode=route_mode,
            profile_items=profile_items,
            provenance_mode=provenance_mode,
        )
    )

    policy_section = _render_working_memory_policy_section(policy, provenance_mode=provenance_mode)
    if policy_section:
        sections.append(policy_section)

    if not suppress_evidence_priority:
        sections.append(_render_evidence_priority_section("## Brainstack Evidence Priority"))

    lookup_semantics_section = _render_lookup_semantics_section(policy.get("lookup_semantics"))
    if lookup_semantics_section:
        sections.append(lookup_semantics_section)

    task_memory_section = _render_task_memory_section(task_rows, provenance_mode=provenance_mode)
    if task_memory_section:
        sections.append(task_memory_section)

    operating_truth_section = _render_operating_truth_section(operating_rows or [], provenance_mode=provenance_mode)
    if operating_truth_section:
        sections.append(operating_truth_section)

    continuation_section = _render_continuation_guidance_section(policy)
    if continuation_section:
        sections.append(continuation_section)

    if exact_contract_section:
        sections.append(exact_contract_section)

    filtered_profile_items = _filtered_profile_items_for_packet(
        profile_items,
        route_mode=route_mode,
        hidden_profile_keys=hidden_profile_keys,
        substrate_profile_keys=substrate_profile_keys,
        canonical_style_present=canonical_style_present,
        native_explicit_style_present=native_explicit_style_present,
        exact_contract_section=exact_contract_section,
        compiled_policy_active=compiled_policy_active,
    )
    profile_section = _render_profile_match_section(
        filtered_profile_items,
        policy=policy,
        route_mode=route_mode,
        provenance_mode=provenance_mode,
    )
    if profile_section:
        sections.append(profile_section)

    sections.extend(
        _render_continuity_or_aggregate_sections(
            route_mode=route_mode,
            matched=matched,
            recent=recent,
            transcript_rows=transcript_rows,
            policy=policy,
            provenance_mode=provenance_mode,
        )
    )

    graph_section = _render_graph_truth_section(graph_rows, policy=policy, provenance_mode=provenance_mode)
    if graph_section:
        sections.append(graph_section)

    packed_corpus = _pack_corpus_rows(
        corpus_rows,
        char_budget=int(policy.get("corpus_char_budget", 360)),
        provenance_mode=provenance_mode,
    )
    if packed_corpus:
        sections.append("## Brainstack Corpus Recall\n" + _render_items(packed_corpus))

    return "\n\n".join(section for section in sections if section.strip())

def build_compression_hint(snapshot: str) -> str:
    snapshot = _trim(snapshot, 500)
    if not snapshot:
        return ""
    return (
        "# Brainstack Continuity Preservation\n"
        "Preserve this continuity snapshot during compression.\n"
        f"- {snapshot}"
    )
