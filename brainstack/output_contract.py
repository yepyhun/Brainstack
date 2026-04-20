from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping


_EMOJI_RANGES = (
    (0x1F1E6, 0x1F1FF),
    (0x1F300, 0x1FAFF),
    (0x2600, 0x27BF),
)
_EMOJI_JOINERS = {0x200D, 0xFE0F}
_FORBIDDEN_PHRASE_RULES = (
    ("knowledge cutoff", "knowledge_cutoff"),
    ("let's dive in", "lets_dive_in"),
    ("lets dive in", "lets_dive_in"),
)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    lowered = text.casefold()
    return any(needle in lowered for needle in needles)


def _is_emoji_char(char: str) -> bool:
    codepoint = ord(char)
    if codepoint in _EMOJI_JOINERS:
        return True
    for start, end in _EMOJI_RANGES:
        if start <= codepoint <= end:
            return True
    return False


def _strip_emoji(text: str) -> str:
    return "".join(char for char in text if not _is_emoji_char(char))


def _strip_markdown_bold(text: str) -> str:
    updated = re.sub(r"\*\*(.*?)\*\*", r"\1", text, flags=re.DOTALL)
    updated = re.sub(r"__(.*?)__", r"\1", updated, flags=re.DOTALL)
    return updated


def build_output_contract(compiled_policy: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(compiled_policy, Mapping):
        return {
            "active": False,
            "dash_policy": "",
            "forbid_emoji": False,
            "forbid_markdown_bold": False,
            "forbidden_phrases": [],
            "sources": [],
        }

    clauses = compiled_policy.get("clauses")
    if not isinstance(clauses, Iterable):
        clauses = []

    dash_policy = ""
    forbid_emoji = False
    forbid_markdown_bold = False
    forbidden_phrase_specs: List[Dict[str, str]] = []
    sources: List[str] = []

    for raw_clause in clauses:
        if not isinstance(raw_clause, Mapping):
            continue
        if str(raw_clause.get("status") or "").strip() not in {"active", "degraded"}:
            continue
        clause_id = str(raw_clause.get("id") or "").strip()
        text = _normalize_text(raw_clause.get("compiled_short_form") or raw_clause.get("text"))
        lowered = text.casefold()
        kind = str(raw_clause.get("kind") or "").strip()
        constraint_code = str(raw_clause.get("constraint_code") or "").strip()
        if not text:
            continue
        if clause_id:
            sources.append(clause_id)
        if kind == "punctuation_policy":
            if constraint_code == "forbid_all_dash_like":
                dash_policy = "forbid_all_dash_like"
            elif not dash_policy and (
                constraint_code == "forbid_em_dash_only"
                or _contains_any(lowered, ("u+2014", "em dash", "u+2013", "en dash"))
            ):
                dash_policy = "forbid_em_dash_only"
        if kind == "forbidden_surface_form" and "emoji" in lowered:
            forbid_emoji = True
        if kind == "formatting_policy" and _contains_any(lowered, ("boldface", "félkövér", "felkövér")):
            forbid_markdown_bold = True
        for phrase, label in _FORBIDDEN_PHRASE_RULES:
            if phrase in lowered:
                forbidden_phrase_specs.append({"label": label, "phrase": phrase, "source_rule_id": clause_id})

    deduped_sources = list(dict.fromkeys(source for source in sources if source))
    deduped_phrase_specs = list(
        {
            (item["label"], item["phrase"], item.get("source_rule_id") or ""): item
            for item in forbidden_phrase_specs
        }.values()
    )
    return {
        "active": bool(deduped_sources),
        "dash_policy": dash_policy,
        "forbid_emoji": forbid_emoji,
        "forbid_markdown_bold": forbid_markdown_bold,
        "forbidden_phrases": deduped_phrase_specs,
        "sources": deduped_sources,
    }


def validate_output_against_contract(
    *,
    content: str,
    compiled_policy: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    original = str(content or "")
    contract = build_output_contract(compiled_policy)
    if not contract["active"] or not original:
        return {
            "content": original,
            "changed": False,
            "applied": False,
            "status": "inactive",
            "blocked": False,
            "can_ship": True,
            "block_reason": "",
            "contract": contract,
            "repairs": [],
            "remaining_violations": [],
        }

    current = original
    repairs: List[Dict[str, Any]] = []
    remaining_violations: List[Dict[str, Any]] = []

    if contract["dash_policy"] == "forbid_em_dash_only":
        replaced = current.replace("—", "-").replace("–", "-")
        if replaced != current:
            repairs.append(
                {
                    "kind": "punctuation_policy",
                    "violation": "em_dash",
                    "repair": "replace_with_hyphen_minus",
                    "enforcement": "repair",
                }
            )
            current = replaced
    elif contract["dash_policy"] == "forbid_all_dash_like" and _contains_any(current, ("—", "–", "-")):
        remaining_violations.append(
            {
                "kind": "punctuation_policy",
                "violation": "dash_like_punctuation",
                "repair": "none",
                "enforcement": "block",
            }
        )

    if contract["forbid_emoji"]:
        replaced = _strip_emoji(current)
        if replaced != current:
            repairs.append(
                {
                    "kind": "forbidden_surface_form",
                    "violation": "emoji",
                    "repair": "strip_emoji_codepoints",
                    "enforcement": "repair",
                }
            )
            current = replaced

    if contract["forbid_markdown_bold"]:
        replaced = _strip_markdown_bold(current)
        if replaced != current:
            repairs.append(
                {
                    "kind": "formatting_policy",
                    "violation": "markdown_bold",
                    "repair": "strip_bold_markers",
                    "enforcement": "repair",
                }
            )
            current = replaced

    lowered_current = current.casefold()
    for item in contract["forbidden_phrases"]:
        phrase = str(item.get("phrase") or "").strip()
        if phrase and phrase in lowered_current:
            remaining_violations.append(
                {
                    "kind": "forbidden_surface_form",
                    "violation": str(item.get("label") or "forbidden_phrase"),
                    "phrase": phrase,
                    "repair": "none",
                    "enforcement": "block",
                    "source_rule_id": str(item.get("source_rule_id") or ""),
                }
            )

    blocked = bool(remaining_violations)
    status = "blocked" if blocked else "repaired" if repairs else "clean"
    return {
        "content": current,
        "changed": current != original,
        "applied": True,
        "status": status,
        "blocked": blocked,
        "can_ship": not blocked,
        "block_reason": "non_repairable_typed_invariant_violation" if blocked else "",
        "contract": contract,
        "repairs": repairs,
        "remaining_violations": remaining_violations,
    }
