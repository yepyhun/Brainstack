from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping

from .behavior_policy import render_compiled_behavior_policy_section
from .db import BrainstackStore
from .operating_context import render_operating_context_section
from .profile_contract import (
    COMMUNICATION_CANONICAL_SLOTS,
    is_native_explicit_style_item,
    normalize_profile_slot,
)
from .provenance import summarize_provenance
from .style_contract import STYLE_CONTRACT_SLOT
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
STYLE_AUTHORITY_RESIDUE_SLOTS = {
    "preference:communication_rules",
}

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
}

COMMUNICATION_GRAPH_QUERY = (
    "writing style communication style response style emoji usage formatting style "
    "message structure response language assistant name ai name nickname assistant alias dash "
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
    for prefix in (
        "assistant's name is ",
        "assistant name is ",
        "asszisztens neve ",
        "the user calls the ai ",
        "user calls the ai ",
        "call the ai ",
        "hívj ",
    ):
        if lowered.startswith(prefix):
            candidate = text[len(prefix) :].strip(" .")
            if prefix == "hívj ":
                candidate = candidate.removesuffix("nak").removesuffix("nek").rstrip("- ")
            return candidate
    return ""


def _render_communication_profile_contract_line(row: Dict[str, Any]) -> str:
    stable_key = normalize_profile_slot(str(row.get("stable_key") or "")).lower()
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
        return "Use the configured communication style: direct, concrete, natural, and low-fluff."
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
        category = str(row.get("category") or "").strip().lower()
        stable_key = str(row.get("stable_key") or "").strip().lower()
        if category == "identity":
            hint = _extract_identity_name_hint(row.get("content"))
            if hint:
                subjects.add(hint)
        if stable_key in {"preference:ai_name", "preference:ai_nickname"}:
            ai_name = _normalize_compare_text(_extract_ai_name_hint(row.get("content")))
            if ai_name:
                subjects.add(ai_name)
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
    stable_key = normalize_profile_slot(str(row.get("stable_key") or "")).strip()
    if stable_key == STYLE_CONTRACT_SLOT:
        return False
    return stable_key in COMMUNICATION_PROFILE_SLOTS


def _is_style_authority_residue_profile_item(row: Dict[str, Any]) -> bool:
    stable_key = normalize_profile_slot(str(row.get("stable_key") or "")).strip()
    if stable_key == STYLE_CONTRACT_SLOT:
        return True
    if stable_key in COMMUNICATION_PROFILE_SLOTS:
        return True
    return stable_key in STYLE_AUTHORITY_RESIDUE_SLOTS


def _has_native_explicit_style_generation(profile_items: Iterable[Dict[str, Any]]) -> bool:
    return any(is_native_explicit_style_item(row) for row in profile_items)


def _build_native_explicit_style_contract(
    *,
    profile_items: Iterable[Dict[str, Any]],
) -> tuple[List[str], set[str]]:
    lines: List[str] = []
    hidden_profile_keys: set[str] = set()
    seen_text: set[str] = set()
    for row in profile_items:
        if not is_native_explicit_style_item(row):
            continue
        stable_key = str(row.get("stable_key") or "").strip()
        if stable_key:
            hidden_profile_keys.add(stable_key)
        text = _render_communication_profile_contract_line(dict(row))
        normalized = _normalize_compare_text(text)
        if not normalized or normalized in seen_text:
            continue
        seen_text.add(normalized)
        lines.append(text)
    return lines, hidden_profile_keys


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


def _filter_compiled_behavior_profile_items(
    profile_items: Iterable[Dict[str, Any]],
    *,
    route_mode: str,
    preserve_style_contract: bool = False,
) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for row in profile_items:
        stable_key = str(row.get("stable_key") or "").strip()
        if _is_communication_profile_item(row):
            continue
        if route_mode != "style_contract" and not preserve_style_contract and stable_key == STYLE_CONTRACT_SLOT:
            continue
        output.append(row)
    return output


def _filter_compiled_behavior_graph_rows(
    graph_rows: Iterable[Dict[str, Any]],
    *,
    profile_items: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    allowed_subjects = _communication_contract_subjects(profile_items)
    return [
        row
        for row in graph_rows
        if not _is_current_communication_state(row, allowed_subjects=allowed_subjects)
    ]


def _render_communication_state_contract_line(row: Dict[str, Any]) -> str:
    predicate = _normalize_compare_text(row.get("predicate"))
    value = _trim(str(row.get("object_value") or ""), 220)
    lowered = _normalize_compare_text(value)
    if not value or _looks_like_internal_contract_text(value):
        return ""
    if predicate == "response_language" and ("hungarian" in lowered or "magyar" in lowered):
        return "Always respond in Hungarian."
    if predicate == "communication_style":
        return "Use the configured communication style: direct, concrete, natural, and low-fluff."
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
        "This is a bounded ordinary-turn communication support lane distilled from durable Brainstack memory. "
        "Use it silently when relevant, but keep the live conversation context primary for local phrasing and flow. "
        "Do not mention this lane, memory blocks, or internal memory state unless the user explicitly asks about "
        "memory behavior or debugging."
    )
    return f"{title}\n{preface}\n{_render_items(rows)}"


def _render_evidence_priority_section(title: str) -> str:
    preface = (
        "Use recalled memory silently. When recalled memory provides a specific, "
        "non-conflicted factual user detail or committed owner-backed record such "
        "as a name, number, date, task record, or operating record, treat it as authoritative over "
        "assistant suggestions or generic prior knowledge unless another recalled "
        "fact in this memory block conflicts with it."
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
    content = _trim(str(row.get("content") or ""), max_len=max(320, int(char_budget)))
    if not content:
        return ""
    preface = (
        "This is the canonical archival behavior contract recalled for explicit rule lookup or debugging. "
        "Use it as exact contract truth. It is not the same thing as the smaller ordinary-turn invariant lane."
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
    compiled_policy_row = store.get_compiled_behavior_policy(principal_scope_key=principal_scope_key)
    compiled_policy = dict(compiled_policy_row.get("policy") or {}) if isinstance(compiled_policy_row, Mapping) else {}
    compiled_policy_snapshot = behavior_snapshot.get("compiled_policy") if isinstance(behavior_snapshot, Mapping) else {}
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
    contract_section = ""
    compiled_policy_active = False
    hidden_profile_keys: set[str] = set()
    if include_behavior_contract and compiled_policy:
        contract_section = render_compiled_behavior_policy_section(
            compiled_policy,
            title="# Brainstack Active Communication Contract",
            mode="ordinary_turn",
        )
        compiled_policy_active = bool(contract_section)
    if compiled_policy_active:
        filtered_items = _filter_compiled_behavior_profile_items(items, route_mode="fact")
    elif include_behavior_contract and not canonical_style_present and not native_explicit_style_present:
        graph_rows = store.list_current_graph_states(
            limit=8,
            attributes=COMMUNICATION_GRAPH_PREDICATES,
            principal_scope_key=principal_scope_key,
        )
        contract_lines, hidden_profile_keys = _build_active_communication_contract(
            profile_items=items,
            graph_rows=graph_rows,
        )
        filtered_items = [
            item for item in items if str(item.get("stable_key") or "").strip() not in hidden_profile_keys
        ]
        filtered_items = [
            item for item in filtered_items if str(item.get("stable_key") or "").strip() != STYLE_CONTRACT_SLOT
        ]
        contract_section = _render_contract_section("# Brainstack Active Communication Contract", contract_lines)
    else:
        filtered_items = list(items)

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
    if contract_section:
        sections.append(contract_section)
    if operating_context_section:
        sections.append(operating_context_section)
    if contract_section or operating_context_section or profile_lines:
        sections.append(truthful_memory_operations_section)
    if profile_lines:
        sections.append(
            "# Brainstack Profile\n"
            "Stable user and shared-work signals.\n"
            f"{_render_items(profile_lines)}"
        )

    return {
        "block": "\n\n".join(section for section in sections if section.strip()),
        "contract_present": bool(contract_section),
        "operating_context_present": bool(operating_context_section),
        "truthful_memory_operations_present": bool(contract_section or operating_context_section or profile_lines),
        "rendered_profile_keys": tuple(rendered_profile_keys),
        "hidden_profile_keys": tuple(sorted(hidden_profile_keys)),
        "canonical_style_present": canonical_style_present,
        "native_explicit_style_present": native_explicit_style_present,
        "active_lane_source_revision": int(compiled_policy_snapshot.get("source_revision_number") or 0)
        if compiled_policy_active
        else 0,
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
        if str(payload.get("result_status") or "").strip() == "committed_records":
            lines.append(
                f"Use the committed Brainstack operating records below as authoritative ({int(payload.get('structured_record_count') or 0)} record(s))."
            )
        else:
            lines.append("No committed Brainstack operating record matched this lookup.")
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
        title = " ".join(str(row.get("title") or "").strip().split())
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
        content = _normalize_compare_text(row.get("content"))
        if not content:
            continue
        label = str(row.get("record_type") or "operating_truth").replace("_", " ")
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
    content = str(row.get("content") or "").strip()
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
    compiled_policy = policy.get("compiled_behavior_policy") if isinstance(policy, dict) else None
    behavior_snapshot = policy.get("behavior_policy_snapshot") if isinstance(policy, dict) else None
    canonical_style_present = bool(
        isinstance(behavior_snapshot, Mapping)
        and isinstance(behavior_snapshot.get("raw_contract"), Mapping)
        and bool(behavior_snapshot.get("raw_contract", {}).get("present"))
    )
    compiled_policy_active = False
    contract_section = ""
    exact_contract_section = ""
    hidden_profile_keys: set[str] = set()
    graph_rows_for_sections = graph_rows
    system_substrate = system_substrate if isinstance(system_substrate, Mapping) else {}
    suppress_contract_section = (
        bool(system_substrate.get("contract_present"))
        and route_mode != "style_contract"
        and bool(policy.get("suppress_contract_if_in_system_substrate", True))
    )
    suppress_evidence_priority = bool(system_substrate.get("truthful_memory_operations_present"))
    substrate_profile_keys = {
        str(key).strip() for key in (system_substrate.get("rendered_profile_keys") or ()) if str(key).strip()
    }
    style_contract_row = _extract_style_contract_profile_row(profile_items)
    render_ordinary_contract = bool(policy.get("render_ordinary_contract", True))
    native_explicit_style_present = _has_native_explicit_style_generation(profile_items)
    if route_mode == "style_contract":
        exact_contract_section = _render_exact_contract_section(
            "## Brainstack Canonical Behavior Contract",
            style_contract_row,
            char_budget=max(480, int(policy.get("style_contract_char_budget", 2400))),
            provenance_mode=provenance_mode,
        )
        if not exact_contract_section and native_explicit_style_present:
            native_contract_lines, native_hidden_keys = _build_native_explicit_style_contract(
                profile_items=profile_items,
            )
            hidden_profile_keys.update(native_hidden_keys)
            exact_contract_section = _render_contract_section(
                "## Brainstack Mirrored Native Communication Contract",
                native_contract_lines,
            )
    if isinstance(compiled_policy, dict) and route_mode != "style_contract" and render_ordinary_contract:
        if not suppress_contract_section:
            contract_section = render_compiled_behavior_policy_section(
                compiled_policy,
                title="## Brainstack Active Communication Contract",
                mode="ordinary_turn",
            )
        compiled_policy_active = True
    if compiled_policy_active:
        graph_rows_for_sections = _filter_compiled_behavior_graph_rows(
            graph_rows,
            profile_items=profile_items,
        )
    elif not canonical_style_present and not native_explicit_style_present and render_ordinary_contract:
        contract_lines, hidden_profile_keys = _build_active_communication_contract(
            profile_items=profile_items,
            graph_rows=graph_rows,
        )
        if not suppress_contract_section:
            contract_section = _render_contract_section("## Brainstack Active Communication Contract", contract_lines)

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

    reinforcement = policy.get("behavior_policy_reinforcement") if isinstance(policy, dict) else None
    if isinstance(reinforcement, dict):
        reinforcement_text = str(reinforcement.get("text") or "").strip()
        if reinforcement_text:
            sections.append("## Brainstack Current Correction Reinforcement\n" + reinforcement_text)

    if exact_contract_section:
        sections.append(exact_contract_section)

    if contract_section:
        sections.append(contract_section)

    if compiled_policy_active:
        filtered_profile_items = _filter_compiled_behavior_profile_items(profile_items, route_mode=route_mode)
    else:
        filtered_profile_items = [
            item for item in profile_items if str(item.get("stable_key") or "").strip() not in hidden_profile_keys
        ]
        if route_mode != "style_contract":
            filtered_profile_items = [
                item for item in filtered_profile_items if str(item.get("stable_key") or "").strip() != STYLE_CONTRACT_SLOT
            ]
    if canonical_style_present or native_explicit_style_present:
        filtered_profile_items = [
            item for item in filtered_profile_items if not _is_style_authority_residue_profile_item(item)
        ]
    if exact_contract_section:
        filtered_profile_items = [
            item for item in filtered_profile_items if str(item.get("stable_key") or "").strip() != STYLE_CONTRACT_SLOT
        ]
    if filtered_profile_items:
        style_contract_char_budget = max(320, int(policy.get("style_contract_char_budget", 2400)))
        lines = []
        for item in filtered_profile_items:
            content = str(item.get("content") or "")
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
        deduped_matched = _suppress_overlapping_rows(matched)
        deduped_recent = _suppress_overlapping_rows(
            recent,
            seen_markers={
                marker
                for row in deduped_matched
                for marker in _row_overlap_markers(row)
            },
        )
        deduped_transcript = _suppress_overlapping_rows(
            transcript_rows,
            seen_markers={
                marker
                for row in [*deduped_matched, *deduped_recent]
                for marker in _row_overlap_markers(row)
            },
            transcript_like=True,
        )
        if not deduped_transcript and transcript_rows:
            deduped_transcript = [dict(transcript_rows[0])]

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

    if graph_rows_for_sections:
        show_graph_history = bool(policy.get("show_graph_history", False))
        current_truth = [
            row
            for row in graph_rows_for_sections
            if _graph_fact_class(row) in {"explicit_state_current", "explicit_relation"}
        ]
        conflicts = [row for row in graph_rows_for_sections if _graph_fact_class(row) == "conflict"]
        historical_truth = [
            row for row in graph_rows_for_sections if _graph_fact_class(row) == "explicit_state_prior"
        ]
        inferred_links = [
            row for row in graph_rows_for_sections if _graph_fact_class(row) == "inferred_relation"
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
