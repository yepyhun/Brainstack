from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping

from .style_contract import STYLE_CONTRACT_DEFAULT_TITLE, list_style_contract_rules


BEHAVIOR_POLICY_SCHEMA_VERSION = 2
BEHAVIOR_POLICY_COMPILER_VERSION = "behavior_policy_v2"
BEHAVIOR_POLICY_STATUS_ACTIVE = "active"
BEHAVIOR_POLICY_COVERAGE_STATUS_COMPILED_ACTIVE = "compiled_active"
DEFAULT_BEHAVIOR_POLICY_CHAR_BUDGET = 2400

_KIND_LABELS = {
    "language_policy": "Language and locale",
    "addressing_policy": "Naming and addressing",
    "tone_policy": "Tone and relationship",
    "content_policy": "Content discipline",
    "verbosity_policy": "Brevity and density",
    "structure_policy": "Structure and composition",
    "formatting_policy": "Formatting and emphasis",
    "punctuation_policy": "Punctuation and symbols",
    "forbidden_surface_form": "Forbidden surface forms",
    "uncertainty_policy": "Uncertainty handling",
    "question_policy": "Follow-up behavior",
    "custom_clause": "Additional explicit rules",
}

_KIND_ORDER = tuple(_KIND_LABELS.keys())
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


def _extract_sections_from_raw_contract(raw_text: str) -> tuple[str, List[Dict[str, Any]]]:
    title = ""
    sections: List[Dict[str, Any]] = []
    current_heading = ""
    current_lines: List[str] = []

    def flush() -> None:
        nonlocal current_heading, current_lines
        lines = _normalize_rule_lines(current_lines)
        if current_heading or lines:
            sections.append({"heading": current_heading, "lines": lines})
        current_heading = ""
        current_lines = []

    for raw_line in str(raw_text or "").splitlines():
        text = raw_line.strip()
        if not text:
            continue
        normalized = _normalize_text(text)
        if not title:
            title = normalized
            continue
        if normalized.endswith(":") and not normalized.startswith("-"):
            flush()
            current_heading = normalized[:-1].strip()
            continue
        if normalized.startswith("-"):
            current_lines.append(normalized[1:].strip())
        else:
            current_lines.append(normalized)

    flush()
    title = title or STYLE_CONTRACT_DEFAULT_TITLE
    if sections:
        return title, sections

    fallback_lines = _normalize_rule_lines(
        line[1:].strip() if _normalize_text(line).startswith("-") else line
        for line in str(raw_text or "").splitlines()[1:]
    )
    if fallback_lines:
        return title, [{"heading": "Rules", "lines": fallback_lines}]
    return title, []


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
    text_lower = _normalize_text(text).casefold()

    if _contains_any(text_lower, ("magyar", "hungarian", "angol", "english")):
        return "language_policy", "direct_language_match"
    if _contains_any(
        text_lower,
        ("szólíts", "hívj", "hivatkozz magadra", "megnevezed magad", "tegez", "én, te, ő", "én te ő", "nagybetű"),
    ):
        return "addressing_policy", "direct_addressing_match"
    if _contains_any(text_lower, ("knowledge cutoff", "chatbot maradvány", "emoji", "let's dive in", "lets dive in")):
        return "forbidden_surface_form", "direct_forbidden_surface_match"
    if _contains_any(text_lower, ("em dash", "dash", "kötőjel", "hyphen", "vessző", "pont", "zárójel", "idézőjel")):
        return "punctuation_policy", "direct_punctuation_match"
    if _contains_any(text_lower, ("boldface", "félkövér", "fejléces felsorolás", "kisbetűs fejlécek", "markdown")):
        return "formatting_policy", "direct_formatting_match"
    if _contains_any(text_lower, ("töltelék", "röviden", "pozitív zárás", "óvatoskodás")):
        return "verbosity_policy", "direct_verbosity_match"
    if _contains_any(text_lower, ("bizonytalan", "bizonytalanság", "hedge")):
        return "uncertainty_policy", "direct_uncertainty_match"
    if _contains_any(text_lower, ("kérdezz", "kérdés", "visszakér")):
        return "question_policy", "direct_question_match"
    if _contains_any(text_lower, ("szervilis", "hangnem", "szolga", "sub", "szerelmes", "autoritás", "direkt", "természetes")):
        return "tone_policy", "direct_tone_match"
    if _contains_any(text_lower, ("konkrét tény", "jelentőségfelfújás", "forrás", "hivatkozás", "elemzés", "kihívások szakasz")):
        return "content_policy", "direct_content_match"
    if _contains_any(text_lower, ("új sor", "külön sor", "hármas szabály", "szinonímacsere", "hamis skála", "töredékes fejlécek")):
        return "structure_policy", "direct_structure_match"

    for marker, kind in _SECTION_FALLBACK_KIND.items():
        if marker in section_lower:
            return kind, "section_fallback"
    return "custom_clause", "explicit_rule_fallback"


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


def _render_projection(clauses: Iterable[Mapping[str, Any]], *, char_budget: int) -> tuple[str, bool, int, int]:
    grouped: Dict[str, List[str]] = {kind: [] for kind in _KIND_ORDER}
    seen_per_kind: Dict[str, set[str]] = {kind: set() for kind in _KIND_ORDER}

    for clause in clauses:
        if str(clause.get("status") or "").strip() != BEHAVIOR_POLICY_STATUS_ACTIVE:
            continue
        kind = str(clause.get("kind") or "custom_clause").strip() or "custom_clause"
        if kind not in grouped:
            kind = "custom_clause"
        short_form = _normalize_text(clause.get("compiled_short_form") or clause.get("text"))
        if not short_form:
            continue
        lowered = short_form.casefold()
        if lowered in seen_per_kind[kind]:
            continue
        seen_per_kind[kind].add(lowered)
        grouped[kind].append(short_form)

    total_rules = sum(len(items) for items in grouped.values())
    if total_rules == 0:
        return "", False, 0, 0

    lines: List[str] = []
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
        for item in items:
            bullet = f"- {item}"
            candidate = "\n".join([*block_lines, bullet])
            if len(candidate) > char_budget:
                break
            block_lines.append(bullet)
            remaining_rules -= 1

        added_rule_count = sum(1 for line in block_lines[len(trial_lines) :] if line.startswith("- "))
        if added_rule_count == 0:
            break
        lines = block_lines

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
    included_rules = max(0, total_rules - remaining_rules)
    return projection_text, truncated, included_rules, total_rules


def compile_behavior_policy(
    *,
    raw_content: str,
    metadata: Mapping[str, Any] | None = None,
    source_storage_key: str = "",
    source_updated_at: str = "",
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

    raw_rules = _build_raw_rules(sections)
    if not raw_rules:
        return None

    clauses: List[Dict[str, Any]] = []
    coverage: List[Dict[str, Any]] = []
    kind_counts: Dict[str, int] = {}
    for raw_rule in raw_rules:
        kind, coverage_reason = _classify_rule(
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
            "hardness": "hard",
            "applies_to": ["text_reply"],
            "status": BEHAVIOR_POLICY_STATUS_ACTIVE,
            "compiled_short_form": str(raw_rule["text"]),
        }
        clauses.append(clause)
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        coverage.append(
            {
                "rule_id": str(raw_rule["id"]),
                "section": str(raw_rule["section"]),
                "raw_text": str(raw_rule["text"]),
                "kind": kind,
                "status": BEHAVIOR_POLICY_COVERAGE_STATUS_COMPILED_ACTIVE,
                "compiled_clause_id": clause_id,
                "reason": coverage_reason,
            }
        )

    projection_budget = max(320, int(char_budget))
    projection_text, truncated, included_rules, total_rules = _render_projection(
        clauses,
        char_budget=projection_budget,
    )
    if not projection_text:
        return None

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
        "status": BEHAVIOR_POLICY_STATUS_ACTIVE,
        "title": title,
        "source_storage_key": str(source_storage_key or "").strip(),
        "source_contract_hash": source_contract_hash,
        "source_contract_updated_at": str(source_updated_at or "").strip(),
        "projection_text": projection_text,
        "projection_char_budget": projection_budget,
        "projection_char_count": len(projection_text),
        "projection_rule_count": included_rules,
        "raw_char_count": len(normalized_content),
        "raw_rule_count": total_rules,
        "truncated": truncated,
        "clauses": clauses,
        "coverage": coverage,
        "kind_counts": kind_counts,
        "no_silent_drop": len(coverage) == total_rules,
        "policy_hash": policy_hash,
    }


def render_compiled_behavior_policy_section(
    policy: Mapping[str, Any] | None,
    *,
    title: str,
) -> str:
    if not isinstance(policy, Mapping):
        return ""
    if str(policy.get("status") or "").strip() != BEHAVIOR_POLICY_STATUS_ACTIVE:
        return ""
    projection_text = str(policy.get("projection_text") or "").strip()
    if not projection_text:
        return ""
    contract_title = _normalize_text(policy.get("title")) or STYLE_CONTRACT_DEFAULT_TITLE
    preface = (
        "This compiled behavior policy is the active ordinary-turn authority derived from the user's "
        "archival behavior contract. Apply it silently in every reply, and let it override default "
        "assistant tone or formatting when there is any conflict. Do not mention this policy, memory "
        "blocks, or internal memory state unless the user explicitly asks about memory behavior or debugging."
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
    compiled_policy = compiled_record.get("policy") if isinstance(compiled_record.get("policy"), Mapping) else {}
    compiled_status = _normalize_text(compiled_policy.get("status") or compiled_record.get("status"))
    compiled_source_hash = _normalize_text(compiled_policy.get("source_contract_hash"))
    projection_text = str(compiled_policy.get("projection_text") or "").strip()

    return {
        "raw_contract": {
            "present": bool(raw_content),
            "title": raw_title or STYLE_CONTRACT_DEFAULT_TITLE,
            "storage_key": str(raw_row.get("storage_key") or ""),
            "stable_key": str(raw_row.get("stable_key") or ""),
            "updated_at": str(raw_row.get("updated_at") or ""),
            "source": str(raw_row.get("source") or ""),
            "content_hash": raw_hash,
            "char_count": len(raw_content),
            "rule_count": len(raw_rules),
            "rules": raw_rules,
        },
        "compiled_policy": {
            "present": bool(compiled_policy),
            "status": compiled_status,
            "active": compiled_status == BEHAVIOR_POLICY_STATUS_ACTIVE and bool(projection_text),
            "title": _normalize_text(compiled_policy.get("title")) or STYLE_CONTRACT_DEFAULT_TITLE,
            "compiler_version": _normalize_text(
                compiled_policy.get("compiler_version") or compiled_record.get("compiler_version")
            ),
            "updated_at": str(compiled_record.get("updated_at") or ""),
            "source_storage_key": str(compiled_policy.get("source_storage_key") or compiled_record.get("source_storage_key") or ""),
            "source_contract_hash": compiled_source_hash,
            "policy_hash": _normalize_text(compiled_policy.get("policy_hash")),
            "projection_text": projection_text,
            "projection_rule_count": int(compiled_policy.get("projection_rule_count") or 0),
            "raw_rule_count": int(compiled_policy.get("raw_rule_count") or 0),
            "no_silent_drop": bool(compiled_policy.get("no_silent_drop")),
        },
        "parity": {
            "raw_present": bool(raw_content),
            "compiled_present": bool(compiled_policy),
            "source_hash_matches_raw": bool(raw_hash and compiled_source_hash and raw_hash == compiled_source_hash),
            "stale": bool(raw_hash and compiled_source_hash and raw_hash != compiled_source_hash),
        },
    }
