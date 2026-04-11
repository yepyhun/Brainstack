from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, Iterable, List, Mapping


logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_PREDICATE_RE = re.compile(r"[^a-z0-9_]+")
_SLOT_RE = re.compile(r"[^a-z0-9:_-]+")
_SLOT_ALIASES = {
    "name": "identity:name",
    "identity_name": "identity:name",
    "identity:name": "identity:name",
    "age": "identity:age",
    "identity_age": "identity:age",
    "identity:age": "identity:age",
    "skill_level": "identity:skill_level",
    "identity_skill_level": "identity:skill_level",
    "identity:skill_level": "identity:skill_level",
    "emoji": "preference:emoji_usage",
    "emojis": "preference:emoji_usage",
    "emoji_usage": "preference:emoji_usage",
    "preference:emoji_usage": "preference:emoji_usage",
    "preference:emojis": "preference:emoji_usage",
    "communication": "preference:communication_style",
    "communication_style": "preference:communication_style",
    "preference:communication_style": "preference:communication_style",
    "formatting": "preference:formatting",
    "humanizer": "preference:formatting",
    "preference:formatting": "preference:formatting",
}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _coerce_confidence(value: Any, *, default: float = 0.75) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _normalize_predicate(value: Any) -> str:
    normalized = _PREDICATE_RE.sub("_", _normalize_text(value).lower()).strip("_")
    return normalized or "related_to"


def _normalize_slot(value: Any) -> str:
    normalized = _SLOT_RE.sub("_", _normalize_text(value).lower()).strip("_")
    return _SLOT_ALIASES.get(normalized, normalized)


def _extract_text_content(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if isinstance(response, Mapping):
        if isinstance(response.get("content"), str):
            return str(response["content"])
        if isinstance(response.get("text"), str):
            return str(response["text"])
    choices = getattr(response, "choices", None)
    if choices:
        message = getattr(choices[0], "message", None)
        if message is not None:
            content = getattr(message, "content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [str(part.get("text", "")) for part in content if isinstance(part, dict)]
                return "\n".join(part for part in parts if part)
    return ""


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    text = _JSON_FENCE_RE.sub("", str(raw_text or "").strip())
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    snippet = text[start : end + 1]
    try:
        payload = json.loads(snippet)
    except json.JSONDecodeError:
        logger.warning("Tier2 extractor returned non-JSON payload")
        return {}
    return payload if isinstance(payload, dict) else {}


def _format_transcript_batch(entries: Iterable[Mapping[str, Any]], *, limit: int) -> str:
    selected = [row for row in entries if _normalize_text(row.get("content"))]
    if not selected:
        return ""
    selected = selected[-limit:]
    blocks: List[str] = []
    for row in selected:
        turn_number = row.get("turn_number", "?")
        kind = _normalize_text(row.get("kind") or "turn")
        content = str(row.get("content") or "").strip()
        if not content:
            continue
        blocks.append(f"[Turn {turn_number} | {kind}]\n{content}")
    return "\n\n".join(blocks)


def _normalize_profile_items(items: Any) -> List[Dict[str, Any]]:
    allowed_categories = {"identity", "preference", "shared_work"}
    normalized: List[Dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, Mapping):
            continue
        category = _normalize_text(raw.get("category")).lower()
        content = _normalize_text(raw.get("content"))
        if category not in allowed_categories or not content:
            continue
        item = {
            "category": category,
            "content": content,
            "confidence": _coerce_confidence(raw.get("confidence"), default=0.78),
            "source": "tier2_llm",
        }
        slot = _normalize_slot(raw.get("slot"))
        if slot:
            item["slot"] = slot
        normalized.append(item)
    return normalized[:8]


def _normalize_states(items: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, Mapping):
            continue
        subject = _normalize_text(raw.get("subject"))
        attribute = _normalize_predicate(raw.get("attribute"))
        value = _normalize_text(raw.get("value"))
        if not subject or not attribute or not value:
            continue
        normalized.append(
            {
                "subject": subject,
                "attribute": attribute,
                "value": value,
                "supersede": bool(raw.get("supersede", False)),
                "confidence": _coerce_confidence(raw.get("confidence"), default=0.82),
            }
        )
    return normalized[:8]


def _normalize_relations(items: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, Mapping):
            continue
        subject = _normalize_text(raw.get("subject"))
        predicate = _normalize_predicate(raw.get("predicate"))
        object_value = _normalize_text(raw.get("object"))
        if not subject or not predicate or not object_value:
            continue
        normalized.append(
            {
                "subject": subject,
                "predicate": predicate,
                "object": object_value,
                "confidence": _coerce_confidence(raw.get("confidence"), default=0.8),
            }
        )
    return normalized[:8]


def _normalize_decisions(items: Any) -> List[str]:
    normalized: List[str] = []
    seen: set[str] = set()
    for raw in items or []:
        value = _normalize_text(raw)
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized[:6]


def _default_llm_caller(*, task: str, messages: list, timeout: float, max_tokens: int) -> Any:
    from agent.auxiliary_client import call_llm

    return call_llm(
        task=task,
        messages=messages,
        temperature=0.0,
        max_tokens=max_tokens,
        timeout=timeout,
    )


def extract_tier2_candidates(
    transcript_entries: Iterable[Mapping[str, Any]],
    *,
    llm_caller: Callable[..., Any] | None = None,
    transcript_limit: int = 8,
    timeout_seconds: float = 15.0,
    max_tokens: int = 900,
    task: str = "flush_memories",
) -> Dict[str, Any]:
    batch = _format_transcript_batch(transcript_entries, limit=transcript_limit)
    if not batch:
        return {
            "profile_items": [],
            "states": [],
            "relations": [],
            "continuity_summary": "",
            "decisions": [],
            "batch_text": "",
        }

    messages = [
        {
            "role": "system",
            "content": (
                "You extract durable memory from multilingual Hermes chat transcripts.\n"
                "Return JSON only. Do not use markdown fences.\n"
                "Schema:\n"
                "{\n"
                '  "profile_items": [{"category":"identity|preference|shared_work","content":"...","slot":"optional-stable-slot","confidence":0.0}],\n'
                '  "states": [{"subject":"...","attribute":"...","value":"...","supersede":true,"confidence":0.0}],\n'
                '  "relations": [{"subject":"...","predicate":"...","object":"...","confidence":0.0}],\n'
                '  "continuity_summary": "short durable summary or empty string",\n'
                '  "decisions": ["durable decision", "..."]\n'
                "}\n"
                "Rules:\n"
                "- prefer durable user facts and current project context\n"
                "- ignore markdown tables, quoted transcript dumps, code, wrappers, and assistant policy chatter\n"
                "- use stable slots only when a profile fact has one obvious durable owner, such as identity:name\n"
                "- use explicit entity names when clear, otherwise use User\n"
                "- keep continuity_summary concise and factual\n"
                "- omit uncertain guesses"
            ),
        },
        {
            "role": "user",
            "content": batch,
        },
    ]

    caller = llm_caller or _default_llm_caller
    response = caller(
        task=task,
        messages=messages,
        timeout=float(timeout_seconds),
        max_tokens=max_tokens,
    )
    payload = _extract_json_object(_extract_text_content(response))
    return {
        "profile_items": _normalize_profile_items(payload.get("profile_items")),
        "states": _normalize_states(payload.get("states")),
        "relations": _normalize_relations(payload.get("relations")),
        "continuity_summary": _normalize_text(payload.get("continuity_summary")),
        "decisions": _normalize_decisions(payload.get("decisions")),
        "batch_text": batch,
    }
