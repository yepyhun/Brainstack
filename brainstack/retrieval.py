from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List

from .db import BrainstackStore
from .profile_contract import COMMUNICATION_CANONICAL_SLOTS
from .provenance import summarize_provenance
from .temporal import record_is_effective_at
from .transcript import trim_text_boundary


def _trim(value: str, max_len: int = 220) -> str:
    return trim_text_boundary(value, max_len=max_len)


def _render_user_first_exchange(content: Any, *, max_len: int) -> str:
    normalized = " ".join(str(content or "").split())
    lowered = normalized.lower()
    user_index = lowered.find("user:")
    assistant_index = lowered.find("assistant:")
    if user_index == -1 or assistant_index == -1 or assistant_index <= user_index:
        return _trim(normalized, max_len=max_len)

    user_part = normalized[user_index:assistant_index].strip()
    assistant_part = normalized[assistant_index:].strip()
    if len(user_part) >= max_len:
        return _trim(user_part, max_len=max_len)
    if len(user_part) + 24 >= max_len:
        return _trim(user_part, max_len=max_len)
    if not assistant_part:
        return _trim(user_part, max_len=max_len)
    combined = f"{user_part} {assistant_part}".strip()
    return _trim(combined, max_len=max_len)


def _render_items(items: Iterable[str]) -> str:
    rows = [item for item in items if item]
    return "\n".join(f"- {item}" for item in rows)


def _render_numbered_items(items: Iterable[str]) -> str:
    rows = [item for item in items if item]
    return "\n".join(f"{index}. {item}" for index, item in enumerate(rows, start=1))


COMMUNICATION_PROFILE_SLOTS = COMMUNICATION_CANONICAL_SLOTS

COMMUNICATION_GRAPH_PREDICATES = {
    "writing_style",
    "communication_style",
    "response_style",
    "emoji_usage",
    "dash_usage",
    "formatting_style",
    "message_structure",
    "pronoun_capitalization",
    "response_language",
    "name",
    "nickname",
}

COMMUNICATION_ASSISTANT_SUBJECTS = {
    "assistant",
    "hermes",
    "bestie",
}

COMMUNICATION_GRAPH_QUERY = (
    "writing style communication style response style emoji usage formatting style "
    "message structure response language assistant name ai name nickname bestie dash "
    "em dash pronoun capitalization"
)

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

_COMMUNICATION_PROFILE_HINTS = (
    "humanizer",
    "emoji",
    "em dash",
    "dash",
    "new line",
    "new lines",
    "line break",
    "paragraph",
    "capitalize pronouns",
    "én",
    " te ",
    " ő ",
    "respond in hungarian",
    "prefer hungarian",
    "magyar",
    "bestie",
    "call the ai",
    "call me",
)


def _normalize_compare_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _extract_identity_name_hint(value: Any) -> str:
    text = " ".join(str(value or "").strip().split())
    lowered = text.lower()
    if lowered.startswith("user's name is "):
        candidate = text[len("User's name is ") :].strip()
        if " (" in candidate:
            candidate = candidate.split(" (", 1)[0].strip()
        return _normalize_compare_text(candidate)
    return ""


def _extract_ai_name_hint(value: Any) -> str:
    text = " ".join(str(value or "").strip().split())
    lowered = text.lower()
    for prefix in ("assistant's name is ", "assistant name is ", "asszisztens neve "):
        if lowered.startswith(prefix):
            return text[len(prefix) :].strip(" .")
    if "bestie" in lowered:
        return "Bestie"
    return ""


def _render_communication_profile_contract_line(row: Dict[str, Any]) -> str:
    stable_key = str(row.get("stable_key") or "").strip().lower()
    content = _trim(str(row.get("content") or ""), 220)
    lowered = _normalize_compare_text(content)
    if not content or _looks_like_internal_contract_text(content):
        return ""
    if stable_key == "preference:response_language":
        if "hungarian" in lowered or "magyar" in lowered:
            return "Always respond in Hungarian."
    if stable_key in {"preference:ai_name", "preference:ai_nickname"}:
        ai_name = _extract_ai_name_hint(content)
        if ai_name:
            return f"Refer to yourself as {ai_name} when naming yourself."
    if stable_key == "preference:communication_style":
        if "humanizer" in lowered:
            return "Use Humanizer style: direct, concrete, natural, and low-fluff."
    if stable_key == "preference:emoji_usage":
        return "Do not use emojis."
    if stable_key == "preference:message_structure":
        return "Put each new thought on its own line."
    if stable_key in {"preference:pronoun_capitalization", "preference:formatting_style"}:
        if any(token in lowered for token in ("én", " te ", " ő ", "pronoun", "nagybetű", "capitalize")):
            return "Capitalize Én, Te, and Ő when you use them."
    if stable_key == "preference:dash_usage":
        return "Do not use dash punctuation in replies."
    return content


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


def _communication_contract_subjects(profile_items: Iterable[Dict[str, Any]]) -> set[str]:
    subjects = set(COMMUNICATION_ASSISTANT_SUBJECTS)
    subjects.update({"user", "the user"})
    for row in profile_items:
        if str(row.get("category") or "").strip().lower() != "identity":
            continue
        hint = _extract_identity_name_hint(row.get("content"))
        if hint:
            subjects.add(hint)
    return subjects


def _is_current_communication_state(row: Dict[str, Any], *, allowed_subjects: set[str]) -> bool:
    if row.get("row_type") != "state":
        return False
    if not row.get("is_current") or not record_is_effective_at(row):
        return False
    subject = _normalize_compare_text(row.get("subject"))
    predicate = _normalize_compare_text(row.get("predicate"))
    if subject not in allowed_subjects or predicate not in COMMUNICATION_GRAPH_PREDICATES:
        return False
    return not _looks_like_internal_contract_text(row.get("object_value"))


def _is_communication_profile_item(row: Dict[str, Any]) -> bool:
    stable_key = str(row.get("stable_key") or "").strip()
    if stable_key in COMMUNICATION_PROFILE_SLOTS:
        return True
    if not stable_key.startswith("preference:"):
        return False
    text = _normalize_compare_text(row.get("content"))
    if not text or _looks_like_internal_contract_text(text):
        return False
    return any(marker in text for marker in _COMMUNICATION_PROFILE_HINTS)


def _build_active_communication_contract(
    *,
    profile_items: Iterable[Dict[str, Any]],
    graph_rows: Iterable[Dict[str, Any]] = (),
) -> tuple[List[str], set[str]]:
    lines: List[str] = []
    hidden_profile_keys: set[str] = set()
    seen_text: set[str] = set()
    allowed_subjects = _communication_contract_subjects(profile_items)

    for row in profile_items:
        if not _is_communication_profile_item(row):
            continue
        stable_key = str(row.get("stable_key") or "").strip()
        if stable_key:
            hidden_profile_keys.add(stable_key)
        text = _render_communication_profile_contract_line(row)
        normalized = _normalize_compare_text(text)
        if not normalized or normalized in seen_text:
            continue
        seen_text.add(normalized)
        lines.append(text)

    for row in graph_rows:
        if not _is_current_communication_state(row, allowed_subjects=allowed_subjects):
            continue
        text = _render_communication_state_contract_line(row)
        normalized = _normalize_compare_text(text)
        if not normalized or normalized in seen_text:
            continue
        seen_text.add(normalized)
        lines.append(text)

    return lines, hidden_profile_keys


def _render_communication_state_contract_line(row: Dict[str, Any]) -> str:
    predicate = _normalize_compare_text(row.get("predicate"))
    value = _trim(str(row.get("object_value") or ""), 220)
    lowered = _normalize_compare_text(value)
    if not value or _looks_like_internal_contract_text(value):
        return ""
    if predicate == "response_language" and ("hungarian" in lowered or "magyar" in lowered):
        return "Always respond in Hungarian."
    if predicate == "communication_style" and "humanizer" in lowered:
        return "Use Humanizer style: direct, concrete, natural, and low-fluff."
    if predicate == "emoji_usage":
        return "Do not use emojis."
    if predicate == "message_structure":
        return "Put each new thought on its own line."
    if predicate == "dash_usage":
        return "Do not use dash punctuation in replies."
    if predicate in {"pronoun_capitalization", "formatting_style"} and any(
        token in lowered for token in ("én", " te ", " ő ", "pronoun", "capitalize", "capitalized", "nagybetű")
    ):
        return "Capitalize Én, Te, and Ő when you use them."
    if predicate in {"name", "nickname"}:
        return f"Refer to yourself as {value} when naming yourself."
    return value


def _render_contract_section(title: str, lines: Iterable[str]) -> str:
    rows = [line for line in lines if line]
    if not rows:
        return ""
    preface = (
        "These are non-optional user-specific behavior rules. Apply them silently in every "
        "reply, and let them override default assistant tone or formatting when there is any "
        "conflict. Do not mention this contract, memory blocks, or internal memory state "
        "unless the user explicitly asks about memory behavior or debugging."
    )
    return f"{title}\n{preface}\n{_render_items(rows)}"


def _render_evidence_priority_section(title: str) -> str:
    preface = (
        "Use recalled memory silently. When recalled memory provides a specific, "
        "non-conflicted user fact such as a name, number, date, or preference, "
        "treat it as authoritative over assistant suggestions or generic prior "
        "knowledge unless another recalled fact in this memory block conflicts "
        "with it."
    )
    return f"{title}\n{preface}"


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
        if row.get("is_current") and record_is_effective_at(row):
            return "explicit_state_current"
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
        if fact_class == "explicit_relation":
            text = f"[relation:explicit] {row['subject']} {row['predicate']} {row['object_value']}"
            lines.append(
                _with_provenance(
                    text,
                    source=str(row.get("source", "")),
                    provenance_mode=provenance_mode,
                    metadata=row.get("metadata"),
                )
            )
            continue
        if fact_class == "inferred_relation":
            reason = str((row.get("metadata") or {}).get("inference_reason") or "").strip()
            extra = f"reason={reason}" if reason else ""
            text = f"[relation:inferred] {row['subject']} {row['predicate']} {row['object_value']}"
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
            continue
        current_marker = "current" if fact_class == "explicit_state_current" else "prior"
        text = f"[state:{current_marker}] {row['subject']} {row['predicate']}={row['object_value']}"
        lines.append(
            _with_provenance(
                text,
                source=str(row.get("source", "")),
                provenance_mode=provenance_mode,
                metadata=row.get("metadata"),
            )
        )
    return lines


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
        content = str(row.get("content") or "").strip()
        snippet_fingerprint = _normalize_compare_text(" ".join(content.split())[:220])
        if snippet_fingerprint and snippet_fingerprint in seen_snippets:
            continue

        remaining = budget - sum(len(item) for item in packed)
        snippet_cap = max(140, min(360, remaining - len(label) - 24))
        line = f"[{row['doc_kind']}] {label}: {_trim(content, snippet_cap)}"
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
        line = f"{prefix} {_trim(str(row.get('content') or ''), snippet_cap)}"
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
        label = f"{prefix} {_render_user_first_exchange(row.get('content') or '', max_len=snippet_cap)}"
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
        content = str(row.get("content") or "")
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
) -> str:
    fetch_limit = max(profile_limit * 3, 10)
    items = store.list_profile_items(limit=fetch_limit, principal_scope_key=principal_scope_key)
    graph_rows = store.list_current_graph_states(
        limit=8,
        attributes=COMMUNICATION_GRAPH_PREDICATES,
        principal_scope_key=principal_scope_key,
    )
    contract_lines, hidden_profile_keys = _build_active_communication_contract(
        profile_items=items,
        graph_rows=graph_rows,
    )
    filtered_items = [item for item in items if str(item.get("stable_key") or "").strip() not in hidden_profile_keys]

    if not contract_lines and not filtered_items:
        return ""

    sections: List[str] = []
    contract_section = _render_contract_section("# Brainstack Active Communication Contract", contract_lines)
    if contract_section:
        sections.append(contract_section)

    lines = []
    for item in filtered_items[:profile_limit]:
        label = item["category"].replace("_", " ")
        lines.append(f"[{label}] {_trim(item['content'], 140)}")
    if lines:
        sections.append(
            "# Brainstack Profile\n"
            "Stable user and shared-work signals.\n"
            f"{_render_items(lines)}"
        )

    return "\n\n".join(section for section in sections if section.strip())


def render_working_memory_block(
    *,
    policy: Dict[str, Any],
    route_mode: str = "fact",
    profile_items: List[Dict[str, Any]],
    matched: List[Dict[str, Any]],
    recent: List[Dict[str, Any]],
    transcript_rows: List[Dict[str, Any]],
    graph_rows: List[Dict[str, Any]],
    corpus_rows: List[Dict[str, Any]],
) -> str:
    sections: List[str] = []
    provenance_mode = str(policy.get("provenance_mode", "compact"))
    contract_lines, hidden_profile_keys = _build_active_communication_contract(
        profile_items=profile_items,
        graph_rows=graph_rows,
    )

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

    sections.append(_render_evidence_priority_section("## Brainstack Evidence Priority"))

    if policy.get("continuation_emphasis"):
        sections.append(
            "## Brainstack Continuation Guidance\n"
            + _render_items(
                [
                    "The user is resuming an existing thread. Carry forward still-relevant concrete details, constraints, named participants, venues, and unresolved tasks from the recalled evidence below.",
                    "Do not invent missing details or add constraints that are not grounded in the recalled evidence.",
                ]
            )
        )

    contract_section = _render_contract_section("## Brainstack Active Communication Contract", contract_lines)
    if contract_section:
        sections.append(contract_section)

    filtered_profile_items = [
        item for item in profile_items if str(item.get("stable_key") or "").strip() not in hidden_profile_keys
    ]
    if filtered_profile_items:
        lines = [
            _with_provenance(
                f"[{item['category'].replace('_', ' ')}] {_trim(item['content'], 160)}",
                source=str(item.get("source", "")),
                provenance_mode=provenance_mode,
                metadata=item.get("metadata"),
            )
            for item in filtered_profile_items
        ]
        sections.append("## Brainstack Profile Match\n" + _render_items(lines))

    if route_mode == "aggregate":
        aggregate_rows = [*matched, *recent, *transcript_rows]
        packed_aggregate = _pack_aggregate_rows(
            aggregate_rows,
            char_budget=max(960, int(policy.get("transcript_char_budget", 320))),
            provenance_mode=provenance_mode,
        )
        if packed_aggregate:
            sections.append(
                "## Brainstack Aggregate Evidence\n"
                "Each numbered line below is a separate recalled item. Combine only the items that actually match the user question.\n"
                + _render_numbered_items(packed_aggregate)
            )
    else:
        if matched:
            lines = _pack_continuity_rows(
                matched,
                char_budget=max(320, min(900, 260 * max(1, len(matched)))),
                provenance_mode=provenance_mode,
            )
            sections.append("## Brainstack Continuity Match\n" + _render_items(lines))

        if recent:
            lines = _pack_continuity_rows(
                recent,
                char_budget=max(240, min(640, 220 * max(1, len(recent)))),
                provenance_mode=provenance_mode,
            )
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
        current_truth = [
            row
            for row in graph_rows
            if _graph_fact_class(row) in {"explicit_state_current", "explicit_relation"}
        ]
        conflicts = [row for row in graph_rows if _graph_fact_class(row) == "conflict"]
        historical_truth = [
            row for row in graph_rows if _graph_fact_class(row) == "explicit_state_prior"
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

        if show_graph_history or conflicts:
            history_lines = _render_graph_rows(historical_truth, provenance_mode=provenance_mode)
            if history_lines:
                graph_sections.append("### Historical Truth\n" + _render_items(history_lines))

        inferred_lines = _render_graph_rows(inferred_links, provenance_mode=provenance_mode)
        if inferred_lines:
            graph_sections.append("### Inferred Links\n" + _render_items(inferred_lines))

        if graph_sections:
            sections.append("## Brainstack Graph Truth\n" + "\n\n".join(graph_sections))

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
