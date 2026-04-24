from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Mapping

from .style_contract import (
    STYLE_CONTRACT_DEFAULT_TITLE,
    extract_style_contract_parts,
    style_contract_cleanliness_issues,
    list_style_contract_rules,
    style_contract_source_rank,
)


BEHAVIOR_POLICY_SCHEMA_VERSION = 2
BEHAVIOR_POLICY_COMPILER_VERSION = "behavior_policy_v2"
BEHAVIOR_POLICY_STATUS_ACTIVE = "active"
BEHAVIOR_POLICY_STATUS_DEGRADED = "degraded"
BEHAVIOR_POLICY_COVERAGE_STATUS_COMPILED_ACTIVE = "compiled_active"
BEHAVIOR_POLICY_PROJECTION_STATUS_INJECTED = "injected"
BEHAVIOR_POLICY_PROJECTION_STATUS_OMITTED_DUE_BUDGET = "omitted_due_budget"
DEFAULT_BEHAVIOR_POLICY_CHAR_BUDGET = 2400
DEFAULT_PINNED_BEHAVIOR_POLICY_CHAR_BUDGET = 720
_POLICY_TOKEN_RE = re.compile(r"[0-9A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]{3,}", re.UNICODE)
_CORRECTION_CUES = (
    "nem ",
    "nem az",
    "most is",
    "még mindig",
    "megint",
    "miért",
    "hiba",
    "rossz",
    "megszeg",
    "megszegted",
    "javítsd",
    "javitsd",
    "isn't",
    "isnt",
    "still",
    "again",
    "wrong",
    "you wrote",
    "used",
)
_TOKEN_STOPWORDS = {
    "hogy",
    "mert",
    "mint",
    "with",
    "this",
    "that",
    "your",
    "have",
    "just",
    "reply",
    "should",
    "most",
    "majd",
    "igen",
}

_KIND_LABELS = {
    "language_policy": "Language and locale",
    "question_policy": "Follow-up behavior",
    "addressing_policy": "Naming and addressing",
    "tone_policy": "Tone and relationship",
    "content_policy": "Content discipline",
    "verbosity_policy": "Brevity and density",
    "structure_policy": "Structure and composition",
    "formatting_policy": "Formatting and emphasis",
    "punctuation_policy": "Punctuation and symbols",
    "forbidden_surface_form": "Forbidden surface forms",
    "uncertainty_policy": "Uncertainty handling",
    "custom_clause": "Additional explicit rules",
}

_KIND_ORDER = (
    "language_policy",
    "question_policy",
    "addressing_policy",
    "tone_policy",
    "content_policy",
    "verbosity_policy",
    "structure_policy",
    "formatting_policy",
    "punctuation_policy",
    "forbidden_surface_form",
    "uncertainty_policy",
    "custom_clause",
)

PINNED_ORDINARY_TURN_KINDS = (
    "language_policy",
    "addressing_policy",
    "content_policy",
    "verbosity_policy",
    "structure_policy",
    "punctuation_policy",
    "formatting_policy",
    "forbidden_surface_form",
    "uncertainty_policy",
)
_SECTION_FALLBACK_KIND = {
    "tartalmi": "content_policy",
    "kommunikációs": "tone_policy",
    "nyelvi": "structure_policy",
    "töltelék": "verbosity_policy",
    "stilus": "tone_policy",
    "stílus": "tone_policy",
}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_rule_lines(values: Any) -> List[str]:
    if isinstance(values, str):
        raw_items = values.splitlines()
    elif isinstance(values, Iterable):
        raw_items = list(values)
    else:
        raw_items = []
    lines: List[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        text = _normalize_text(raw)
        if not text:
            continue
        lowered = text.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        lines.append(text)
    return lines


def _slug(value: str) -> str:
    output = "".join(char.lower() if char.isalnum() else "-" for char in value)
    while "--" in output:
        output = output.replace("--", "-")
    return output.strip("-") or "rules"


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    lowered = text.casefold()
    return any(needle in lowered for needle in needles)


def _sanitize_policy_surface(text: Any) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""
    return normalized.replace("—", "U+2014 EM DASH").replace("–", "U+2013 EN DASH")


def _resolve_punctuation_constraint(text: str) -> str:
    del text
    return "surface_text"


def _extract_sections_from_raw_contract(raw_text: str) -> tuple[str, List[Dict[str, Any]]]:
    parts = extract_style_contract_parts(raw_text)
    if parts is None:
        return STYLE_CONTRACT_DEFAULT_TITLE, []
    sections = [
        {
            "heading": _normalize_text(section.get("heading")),
            "lines": _normalize_rule_lines(section.get("lines")),
        }
        for section in parts.get("sections") or ()
        if isinstance(section, Mapping)
    ]
    return _normalize_text(parts.get("title")) or STYLE_CONTRACT_DEFAULT_TITLE, sections


def _sections_from_metadata(metadata: Mapping[str, Any] | None) -> tuple[str, List[Dict[str, Any]]]:
    if not isinstance(metadata, Mapping):
        return "", []
    title = _normalize_text(metadata.get("style_contract_title"))
    raw_sections = metadata.get("style_contract_sections")
    sections: List[Dict[str, Any]] = []
    if isinstance(raw_sections, Iterable):
        for raw_section in raw_sections:
            if not isinstance(raw_section, Mapping):
                continue
            heading = _normalize_text(raw_section.get("heading"))
            lines = _normalize_rule_lines(raw_section.get("lines"))
            if not heading and not lines:
                continue
            sections.append({"heading": heading, "lines": lines})
    return title, sections


def _classify_rule(section: str, text: str) -> tuple[str, str]:
    section_lower = _normalize_text(section).casefold()
    del text

    for marker, kind in _SECTION_FALLBACK_KIND.items():
        if marker in section_lower:
            return kind, "section_fallback"
    return "custom_clause", "explicit_rule_fallback"


def _compile_short_form(*, kind: str, text: str) -> str:
    normalized = _normalize_text(text)
    return _sanitize_policy_surface(normalized)


def _build_raw_rules(sections: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    raw_rules: List[Dict[str, Any]] = []
    order = 0
    for section_index, section in enumerate(sections, start=1):
        heading = str(section.get("heading") or "").strip() or f"rules-{section_index}"
        heading_slug = _slug(heading)
        for line_index, line in enumerate(section.get("lines") or (), start=1):
            normalized_line = _normalize_text(line)
            if not normalized_line:
                continue
            order += 1
            raw_rules.append(
                {
                    "id": f"{heading_slug}-{line_index:02d}",
                    "order": order,
                    "section": heading,
                    "section_slug": heading_slug,
                    "text": normalized_line,
                }
            )
    return raw_rules


def _render_projection(
    clauses: Iterable[Mapping[str, Any]],
    *,
    char_budget: int,
) -> tuple[str, bool, List[str], int]:
    grouped: Dict[str, List[Dict[str, str]]] = {kind: [] for kind in _KIND_ORDER}

    for clause in clauses:
        if str(clause.get("status") or "").strip() != BEHAVIOR_POLICY_STATUS_ACTIVE:
            continue
        kind = str(clause.get("kind") or "custom_clause").strip() or "custom_clause"
        if kind not in grouped:
            kind = "custom_clause"
        short_form = _sanitize_policy_surface(clause.get("compiled_short_form") or clause.get("text"))
        if not short_form:
            continue
        grouped[kind].append({"id": str(clause.get("id") or ""), "text": short_form})

    total_rules = sum(len(items) for items in grouped.values())
    if total_rules == 0:
        return "", False, [], 0

    lines: List[str] = []
    included_rule_ids: List[str] = []
    remaining_rules = total_rules
    for kind in _KIND_ORDER:
        items = grouped[kind]
        if not items:
            continue
        block_prefix = [""] if lines else []
        block_prefix.append(f"{_KIND_LABELS[kind]}:")
        trial_lines = [*lines]
        block_fits = True
        for prefix_line in block_prefix:
            candidate = "\n".join([*trial_lines, prefix_line]) if trial_lines else prefix_line
            if len(candidate) > char_budget:
                block_fits = False
                break
            trial_lines.append(prefix_line)
        if not block_fits:
            break

        block_lines = [*trial_lines]
        kind_rule_ids: List[str] = []
        for item in items:
            bullet = f"- {item['text']}"
            candidate = "\n".join([*block_lines, bullet])
            if len(candidate) > char_budget:
                break
            block_lines.append(bullet)
            kind_rule_ids.append(item["id"])
            remaining_rules -= 1

        added_rule_count = sum(1 for line in block_lines[len(trial_lines) :] if line.startswith("- "))
        if added_rule_count == 0:
            break
        lines = block_lines
        included_rule_ids.extend(kind_rule_ids)

        if remaining_rules <= 0:
            break

    truncated = remaining_rules > 0
    if truncated:
        suffix = f"... ({remaining_rules} additional compiled rules omitted)"
        while lines:
            candidate = "\n".join([*lines, suffix])
            if len(candidate) <= char_budget:
                lines.append(suffix)
                break
            removed = lines.pop()
            if removed.startswith("- "):
                remaining_rules += 1
                suffix = f"... ({remaining_rules} additional compiled rules omitted)"
        if not lines:
            lines = [suffix] if len(suffix) <= char_budget else ["..."]

    projection_text = "\n".join(lines).strip()
    return projection_text, truncated, included_rule_ids, total_rules


def build_pinned_behavior_policy_view(
    policy: Mapping[str, Any] | None,
    *,
    char_budget: int = DEFAULT_PINNED_BEHAVIOR_POLICY_CHAR_BUDGET,
) -> Dict[str, Any] | None:
    if not isinstance(policy, Mapping):
        return None

    status = str(policy.get("status") or "").strip()
    if status not in {BEHAVIOR_POLICY_STATUS_ACTIVE, BEHAVIOR_POLICY_STATUS_DEGRADED}:
        return None

    raw_clauses = policy.get("clauses")
    if not isinstance(raw_clauses, Iterable):
        return None

    pinned_clauses = [
        dict(clause)
        for clause in raw_clauses
        if isinstance(clause, Mapping)
        and str(clause.get("status") or "").strip() == BEHAVIOR_POLICY_STATUS_ACTIVE
        and str(clause.get("kind") or "").strip() in PINNED_ORDINARY_TURN_KINDS
    ]
    if not pinned_clauses:
        return None

    projection_text, truncated, included_rule_ids, total_rules = _render_projection(
        pinned_clauses,
        char_budget=max(240, int(char_budget)),
    )
    if not projection_text:
        return None

    included_rule_id_set = {rule_id for rule_id in included_rule_ids if rule_id}
    return {
        "title": _normalize_text(policy.get("title")) or STYLE_CONTRACT_DEFAULT_TITLE,
        "status": BEHAVIOR_POLICY_STATUS_ACTIVE if not truncated else BEHAVIOR_POLICY_STATUS_DEGRADED,
        "projection_text": projection_text,
        "projection_char_budget": max(240, int(char_budget)),
        "projection_rule_count": len(included_rule_id_set),
        "raw_rule_count": total_rules,
        "omitted_rule_count": max(0, total_rules - len(included_rule_id_set)),
        "truncated": truncated,
        "source_contract_hash": str(policy.get("source_contract_hash") or "").strip(),
        "kinds": list(PINNED_ORDINARY_TURN_KINDS),
    }


def compile_behavior_policy(
    *,
    raw_content: str,
    metadata: Mapping[str, Any] | None = None,
    source_storage_key: str = "",
    source_updated_at: str = "",
    source_revision_number: int = 0,
    char_budget: int = DEFAULT_BEHAVIOR_POLICY_CHAR_BUDGET,
) -> Dict[str, Any] | None:
    normalized_content = str(raw_content or "").strip()
    if not normalized_content:
        return None

    title_from_metadata, sections = _sections_from_metadata(metadata)
    if not sections:
        parsed_title, sections = _extract_sections_from_raw_contract(normalized_content)
    else:
        parsed_title = ""
    title = title_from_metadata or parsed_title or STYLE_CONTRACT_DEFAULT_TITLE
    if not sections:
        return None
    if style_contract_cleanliness_issues(
        raw_text=normalized_content,
        metadata={
            "style_contract_title": title,
            "style_contract_sections": sections,
        },
    ):
        return None

    raw_rules = _build_raw_rules(sections)
    if not raw_rules:
        return None

    clauses: List[Dict[str, Any]] = []
    kind_counts: Dict[str, int] = {}
    for raw_rule in raw_rules:
        kind, _coverage_reason = _classify_rule(
            str(raw_rule.get("section") or ""),
            str(raw_rule.get("text") or ""),
        )
        clause_id = str(raw_rule["id"])
        clause = {
            "id": clause_id,
            "source_rule_id": str(raw_rule["id"]),
            "source_order": int(raw_rule["order"]),
            "section": str(raw_rule["section"]),
            "text": str(raw_rule["text"]),
            "kind": kind,
            "constraint_code": _resolve_punctuation_constraint(str(raw_rule["text"])) if kind == "punctuation_policy" else "",
            "hardness": "hard",
            "applies_to": ["text_reply"],
            "status": BEHAVIOR_POLICY_STATUS_ACTIVE,
            "compiled_short_form": _compile_short_form(kind=kind, text=str(raw_rule["text"])),
        }
        clauses.append(clause)
        kind_counts[kind] = kind_counts.get(kind, 0) + 1

    projection_budget = max(320, int(char_budget))
    projection_text, truncated, included_rule_ids, total_rules = _render_projection(
        clauses,
        char_budget=projection_budget,
    )
    if not projection_text:
        return None
    included_rule_id_set = {rule_id for rule_id in included_rule_ids if rule_id}
    coverage: List[Dict[str, Any]] = []
    for raw_rule, clause in zip(raw_rules, clauses):
        _kind, coverage_reason = _classify_rule(
            str(raw_rule.get("section") or ""),
            str(raw_rule.get("text") or ""),
        )
        clause_id = str(clause.get("id") or "")
        projection_status = (
            BEHAVIOR_POLICY_PROJECTION_STATUS_INJECTED
            if clause_id in included_rule_id_set
            else BEHAVIOR_POLICY_PROJECTION_STATUS_OMITTED_DUE_BUDGET
        )
        coverage.append(
            {
                "rule_id": str(raw_rule["id"]),
                "section": str(raw_rule["section"]),
                "raw_text": str(raw_rule["text"]),
                "kind": str(clause.get("kind") or "custom_clause"),
                "status": BEHAVIOR_POLICY_COVERAGE_STATUS_COMPILED_ACTIVE,
                "compile_status": BEHAVIOR_POLICY_COVERAGE_STATUS_COMPILED_ACTIVE,
                "projection_status": projection_status,
                "ordinary_turn_enforced": projection_status == BEHAVIOR_POLICY_PROJECTION_STATUS_INJECTED,
                "compiled_clause_id": clause_id,
                "reason": coverage_reason,
            }
        )
    omitted_rule_count = max(0, total_rules - len(included_rule_id_set))
    no_compile_drop = len(coverage) == total_rules
    no_projection_drop = omitted_rule_count == 0
    policy_status = BEHAVIOR_POLICY_STATUS_ACTIVE if no_projection_drop else BEHAVIOR_POLICY_STATUS_DEGRADED

    source_contract_hash = hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
    policy_hash = hashlib.sha256(
        json.dumps(
            {
                "compiler_version": BEHAVIOR_POLICY_COMPILER_VERSION,
                "source_contract_hash": source_contract_hash,
                "clauses": clauses,
                "projection_text": projection_text,
            },
            ensure_ascii=True,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": BEHAVIOR_POLICY_SCHEMA_VERSION,
        "compiler_version": BEHAVIOR_POLICY_COMPILER_VERSION,
        "status": policy_status,
        "title": title,
        "source_storage_key": str(source_storage_key or "").strip(),
        "source_contract_hash": source_contract_hash,
        "source_contract_updated_at": str(source_updated_at or "").strip(),
        "source_revision_number": int(source_revision_number or 0),
        "projection_text": projection_text,
        "projection_char_budget": projection_budget,
        "projection_char_count": len(projection_text),
        "projection_rule_count": len(included_rule_id_set),
        "raw_char_count": len(normalized_content),
        "raw_rule_count": total_rules,
        "omitted_rule_count": omitted_rule_count,
        "truncated": truncated,
        "clauses": clauses,
        "coverage": coverage,
        "kind_counts": kind_counts,
        "no_compile_drop": no_compile_drop,
        "no_projection_drop": no_projection_drop,
        "no_silent_drop": no_compile_drop,
        "policy_hash": policy_hash,
    }


def render_compiled_behavior_policy_section(
    policy: Mapping[str, Any] | None,
    *,
    title: str,
    mode: str = "full",
) -> str:
    if mode == "ordinary_turn":
        pinned_view = build_pinned_behavior_policy_view(policy)
        if not isinstance(pinned_view, Mapping):
            return ""
        projection_text = str(pinned_view.get("projection_text") or "").strip()
        if not projection_text:
            return ""
        contract_title = _normalize_text(pinned_view.get("title")) or STYLE_CONTRACT_DEFAULT_TITLE
        preface = (
            "This is a bounded ordinary-turn invariant subset derived from the user's canonical behavior contract. "
            "Use it silently as support on ordinary turns, but keep the live conversation context primary for local "
            "phrasing, short-range flow, and social reasoning. Do not mention this invariant lane, memory blocks, "
            "or internal memory state unless the user explicitly asks about memory behavior or debugging."
        )
        if str(pinned_view.get("status") or "").strip() == BEHAVIOR_POLICY_STATUS_DEGRADED:
            preface += (
                " Status: narrowed by budget. Only the included high-value invariant subset below is kept on the "
                "ordinary-turn hot path."
            )
        return f"{title}\n{contract_title}\n{preface}\n{projection_text}"

    if not isinstance(policy, Mapping):
        return ""
    status = str(policy.get("status") or "").strip()
    if status not in {BEHAVIOR_POLICY_STATUS_ACTIVE, BEHAVIOR_POLICY_STATUS_DEGRADED}:
        return ""
    projection_text = str(policy.get("projection_text") or "").strip()
    if not projection_text:
        return ""
    contract_title = _normalize_text(policy.get("title")) or STYLE_CONTRACT_DEFAULT_TITLE
    preface = (
        "This compiled behavior policy is a derived projection of the user's archival behavior contract. "
        "Use it only as a derived view of the canonical contract, not as a substitute for exact contract recall."
    )
    if status == BEHAVIOR_POLICY_STATUS_DEGRADED:
        preface += (
            " Status: degraded. Some active rules did not fit into the bounded projection, so this view is incomplete."
        )
    return f"{title}\n{contract_title}\n{preface}\n{projection_text}"


def build_behavior_policy_snapshot(
    *,
    raw_contract_row: Mapping[str, Any] | None,
    compiled_policy_record: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    raw_row = dict(raw_contract_row or {})
    raw_content = str(raw_row.get("content") or "").strip()
    raw_metadata = raw_row.get("metadata") if isinstance(raw_row.get("metadata"), Mapping) else {}
    raw_title, raw_sections = _sections_from_metadata(raw_metadata)
    if not raw_sections:
        parsed_title, raw_sections = _extract_sections_from_raw_contract(raw_content)
        raw_title = raw_title or parsed_title
    raw_rules = list_style_contract_rules(raw_text=raw_content, metadata=raw_metadata)
    raw_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest() if raw_content else ""

    compiled_record = dict(compiled_policy_record or {})
    raw_compiled_policy = compiled_record.get("policy")
    compiled_policy: Mapping[str, Any] = raw_compiled_policy if isinstance(raw_compiled_policy, Mapping) else {}
    compiled_status = _normalize_text(compiled_policy.get("status") or compiled_record.get("status"))
    compiled_source_hash = _normalize_text(compiled_policy.get("source_contract_hash"))
    projection_text = str(compiled_policy.get("projection_text") or "").strip()
    no_compile_drop = bool(compiled_policy.get("no_compile_drop", compiled_policy.get("no_silent_drop")))
    no_projection_drop = bool(
        compiled_policy.get("no_projection_drop", not bool(compiled_policy.get("truncated")))
    )
    omitted_rule_count = int(
        compiled_policy.get("omitted_rule_count")
        or max(
            0,
            int(compiled_policy.get("raw_rule_count") or 0) - int(compiled_policy.get("projection_rule_count") or 0),
        )
    )

    return {
        "raw_contract": {
            "present": bool(raw_content),
            "title": raw_title or STYLE_CONTRACT_DEFAULT_TITLE,
            "storage_key": str(raw_row.get("storage_key") or ""),
            "stable_key": str(raw_row.get("stable_key") or ""),
            "revision_number": int(raw_row.get("revision_number") or 0),
            "status": str(raw_row.get("status") or ""),
            "updated_at": str(raw_row.get("updated_at") or ""),
            "source": str(raw_row.get("source") or ""),
            "source_rank": style_contract_source_rank(raw_row.get("source")),
            "content_hash": raw_hash,
            "char_count": len(raw_content),
            "rule_count": len(raw_rules),
            "rules": raw_rules,
        },
        "compiled_policy": {
            "present": bool(compiled_policy),
            "status": compiled_status,
            "active": compiled_status in {BEHAVIOR_POLICY_STATUS_ACTIVE, BEHAVIOR_POLICY_STATUS_DEGRADED}
            and bool(projection_text),
            "degraded": compiled_status == BEHAVIOR_POLICY_STATUS_DEGRADED,
            "title": _normalize_text(compiled_policy.get("title")) or STYLE_CONTRACT_DEFAULT_TITLE,
            "compiler_version": _normalize_text(
                compiled_policy.get("compiler_version") or compiled_record.get("compiler_version")
            ),
            "updated_at": str(compiled_record.get("updated_at") or ""),
            "source_storage_key": str(compiled_policy.get("source_storage_key") or compiled_record.get("source_storage_key") or ""),
            "source_contract_hash": compiled_source_hash,
            "source_revision_number": int(compiled_policy.get("source_revision_number") or 0),
            "policy_hash": _normalize_text(compiled_policy.get("policy_hash")),
            "projection_text": projection_text,
            "projection_rule_count": int(compiled_policy.get("projection_rule_count") or 0),
            "raw_rule_count": int(compiled_policy.get("raw_rule_count") or 0),
            "omitted_rule_count": omitted_rule_count,
            "no_compile_drop": no_compile_drop,
            "no_projection_drop": no_projection_drop,
            "no_silent_drop": bool(compiled_policy.get("no_silent_drop", no_compile_drop)),
        },
        "parity": {
            "raw_present": bool(raw_content),
            "compiled_present": bool(compiled_policy),
            "source_hash_matches_raw": bool(raw_hash and compiled_source_hash and raw_hash == compiled_source_hash),
            "stale": bool(raw_hash and compiled_source_hash and raw_hash != compiled_source_hash),
            "source_revision_matches_raw": bool(
                int(raw_row.get("revision_number") or 0)
                and int(compiled_policy.get("source_revision_number") or 0)
                and int(raw_row.get("revision_number") or 0) == int(compiled_policy.get("source_revision_number") or 0)
            ),
        },
    }


def _tokenize_policy_text(value: Any) -> List[str]:
    tokens = [token.casefold() for token in _POLICY_TOKEN_RE.findall(_normalize_text(value))]
    return [token for token in tokens if token not in _TOKEN_STOPWORDS]


def _looks_like_correction_query(query: str) -> bool:
    lowered = _normalize_text(query).casefold()
    if not lowered:
        return False
    return any(cue in lowered for cue in _CORRECTION_CUES) or lowered.endswith("?")


def _correction_clause_score(*, query: str, clause_text: str) -> int:
    query_lower = _normalize_text(query).casefold()
    if not query_lower or not clause_text:
        return 0
    score = 0
    for token in _tokenize_policy_text(clause_text):
        if token in query_lower or query_lower in token:
            score += 1
    return score


def build_behavior_policy_reinforcement(
    *,
    query: str,
    compiled_policy: Mapping[str, Any] | None,
) -> Dict[str, Any] | None:
    if not isinstance(compiled_policy, Mapping):
        return None
    if not _looks_like_correction_query(query):
        return None
    clauses = compiled_policy.get("clauses")
    if not isinstance(clauses, Iterable):
        return None

    scored: List[tuple[int, Dict[str, Any]]] = []
    for raw_clause in clauses:
        if not isinstance(raw_clause, Mapping):
            continue
        if str(raw_clause.get("status") or "").strip() != BEHAVIOR_POLICY_STATUS_ACTIVE:
            continue
        clause_text = _sanitize_policy_surface(raw_clause.get("compiled_short_form") or raw_clause.get("text"))
        score = _correction_clause_score(query=query, clause_text=clause_text)
        if score <= 0:
            continue
        scored.append((score, {"id": str(raw_clause.get("id") or ""), "text": clause_text}))

    if not scored:
        return None

    scored.sort(key=lambda item: (item[0], item[1]["id"]), reverse=True)
    matched = [item[1] for item in scored[:2]]
    lines = [
        "The user just corrected a drift against the active behavior policy. For this reply, re-apply these rules strictly:",
        *[f"- {item['text']}" for item in matched],
    ]
    return {
        "mode": "session_reinforcement",
        "matched_clause_ids": [item["id"] for item in matched if item["id"]],
        "text": "\n".join(lines),
    }
