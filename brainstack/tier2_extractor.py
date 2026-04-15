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
            content = str(response["content"]).strip()
            if content:
                return content
        if isinstance(response.get("text"), str):
            text = str(response["text"]).strip()
            if text:
                return text
        for field in ("reasoning", "reasoning_content"):
            if isinstance(response.get(field), str):
                reasoning_text = str(response[field]).strip()
                if reasoning_text:
                    return reasoning_text
        details = response.get("reasoning_details")
        if isinstance(details, list):
            parts: List[str] = []
            for detail in details:
                if not isinstance(detail, Mapping):
                    continue
                summary = detail.get("summary") or detail.get("content") or detail.get("text")
                if isinstance(summary, str) and summary.strip():
                    parts.append(summary.strip())
            if parts:
                return "\n\n".join(parts)
    choices = getattr(response, "choices", None)
    if choices:
        message = getattr(choices[0], "message", None)
        if message is not None:
            content = getattr(message, "content", "")
            if isinstance(content, str) and content.strip():
                return content
            if isinstance(content, list):
                parts = [str(part.get("text", "")) for part in content if isinstance(part, dict)]
                joined = "\n".join(part for part in parts if part)
                if joined.strip():
                    return joined
            for field in ("reasoning", "reasoning_content"):
                value = getattr(message, field, None)
                if isinstance(value, str) and value.strip():
                    return value
            details = getattr(message, "reasoning_details", None)
            if isinstance(details, list):
                parts = []
                for detail in details:
                    if not isinstance(detail, Mapping):
                        continue
                    summary = detail.get("summary") or detail.get("content") or detail.get("text")
                    if isinstance(summary, str) and summary.strip():
                        parts.append(summary.strip())
                if parts:
                    return "\n\n".join(parts)
    return ""


def _repair_truncated_json_object(text: str) -> Dict[str, Any]:
    start = text.find("{")
    if start == -1:
        return {}
    raw = text[start:]
    lower_bound = max(1, len(raw) - 800)
    for end in range(len(raw), lower_bound - 1, -1):
        candidate = raw[:end].rstrip()
        if not candidate:
            continue
        while candidate and candidate[-1] in {",", ":"}:
            candidate = candidate[:-1].rstrip()
        if not candidate:
            continue

        stack: List[str] = []
        in_string = False
        escape = False
        for char in candidate:
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char in "{[":
                stack.append("}" if char == "{" else "]")
            elif char in "}]":
                if stack and stack[-1] == char:
                    stack.pop()
                else:
                    stack = []
                    break
        else:
            repaired = candidate
            if in_string:
                repaired += '"'
            repaired += "".join(reversed(stack))
            try:
                payload = json.loads(repaired)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    return {}


def _extract_json_object_with_status(raw_text: str, *, context: str = "") -> tuple[Dict[str, Any], str]:
    text = _JSON_FENCE_RE.sub("", str(raw_text or "").strip())
    if not text:
        return {}, "empty_text"
    try:
        payload = json.loads(text)
        return (payload if isinstance(payload, dict) else {}), "json_object"
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        repaired = _repair_truncated_json_object(text)
        if repaired:
            return repaired, "json_repaired"
        if context:
            logger.warning("Tier2 extractor returned non-JSON payload (%s): %s", context, text[:240])
        else:
            logger.warning("Tier2 extractor returned non-JSON payload: %s", text[:240])
        return {}, "non_json"
    snippet = text[start : end + 1]
    try:
        payload = json.loads(snippet)
    except json.JSONDecodeError:
        repaired = _repair_truncated_json_object(text)
        if repaired:
            return repaired, "json_repaired"
        if context:
            logger.warning("Tier2 extractor returned non-JSON payload (%s): %s", context, text[:240])
        else:
            logger.warning("Tier2 extractor returned non-JSON payload: %s", text[:240])
        return {}, "non_json"
    return (payload if isinstance(payload, dict) else {}), "json_snippet"


def _extract_json_object(raw_text: str, *, context: str = "") -> Dict[str, Any]:
    payload, _ = _extract_json_object_with_status(raw_text, context=context)
    return payload


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


def _normalize_inferred_relations(items: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, Mapping):
            continue
        subject = _normalize_text(raw.get("subject"))
        predicate = _normalize_predicate(raw.get("predicate"))
        object_value = _normalize_text(raw.get("object"))
        if not subject or not predicate or not object_value:
            continue
        item: Dict[str, Any] = {
            "subject": subject,
            "predicate": predicate,
            "object": object_value,
            "confidence": _coerce_confidence(raw.get("confidence"), default=0.62),
        }
        reason = _normalize_text(raw.get("reason"))
        if reason:
            item["metadata"] = {"inference_reason": reason}
        normalized.append(item)
    return normalized[:4]


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


def _normalize_temporal_events(
    items: Any,
    *,
    transcript_entries: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    entries_by_turn: Dict[int, Mapping[str, Any]] = {}
    for row in transcript_entries:
        try:
            turn_number = int(row.get("turn_number") or 0)
        except (TypeError, ValueError):
            turn_number = 0
        if turn_number > 0 and turn_number not in entries_by_turn:
            entries_by_turn[turn_number] = row

    normalized: List[Dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, Mapping):
            continue
        try:
            turn_number = int(raw.get("turn_number") or 0)
        except (TypeError, ValueError):
            turn_number = 0
        content = _normalize_text(raw.get("content"))
        if turn_number <= 0 or not content:
            continue
        transcript_row = entries_by_turn.get(turn_number)
        if transcript_row is None:
            continue
        created_at = _normalize_text(transcript_row.get("created_at"))
        item: Dict[str, Any] = {
            "turn_number": turn_number,
            "content": content,
            "confidence": _coerce_confidence(raw.get("confidence"), default=0.76),
            "metadata": {"event_turn_number": turn_number},
        }
        if created_at:
            item["temporal"] = {"observed_at": created_at}
        normalized.append(item)
    return normalized[:8]


_TYPED_ENTITY_NUMERIC_KEYS = {
    "distance_miles",
    "amount_usd",
    "duration_days",
    "count",
    "quantity",
}


def _normalize_typed_entity_attributes(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, Mapping):
        return {}
    normalized: Dict[str, str] = {}
    for key, value in raw.items():
        attribute = _normalize_predicate(key)
        text = _normalize_text(value)
        if not attribute or not text:
            continue
        if attribute in _TYPED_ENTITY_NUMERIC_KEYS:
            match = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?", text)
            if match:
                text = match.group(0).replace(",", "")
        normalized[attribute] = text
        if len(normalized) >= 4:
            break
    return normalized


def _normalize_typed_entities(
    items: Any,
    *,
    transcript_entries: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    entries_by_turn: Dict[int, Mapping[str, Any]] = {}
    for row in transcript_entries:
        try:
            turn_number = int(row.get("turn_number") or 0)
        except (TypeError, ValueError):
            turn_number = 0
        if turn_number > 0 and turn_number not in entries_by_turn:
            entries_by_turn[turn_number] = row

    normalized: List[Dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, Mapping):
            continue
        try:
            turn_number = int(raw.get("turn_number") or 0)
        except (TypeError, ValueError):
            turn_number = 0
        transcript_row = entries_by_turn.get(turn_number)
        if turn_number <= 0 or transcript_row is None:
            continue
        entity_type = _normalize_predicate(raw.get("entity_type"))
        if not entity_type:
            continue
        name = _normalize_text(raw.get("name")) or f"{entity_type} turn {turn_number}"
        attributes = _normalize_typed_entity_attributes(raw.get("attributes"))
        if not attributes:
            continue
        subject = _normalize_text(raw.get("subject")) or "User"
        created_at = _normalize_text(transcript_row.get("created_at"))
        item: Dict[str, Any] = {
            "turn_number": turn_number,
            "name": name,
            "entity_type": entity_type,
            "subject": subject,
            "attributes": attributes,
            "confidence": _coerce_confidence(raw.get("confidence"), default=0.78),
            "metadata": {"event_turn_number": turn_number},
        }
        if created_at:
            item["temporal"] = {"observed_at": created_at}
        normalized.append(item)
    return normalized[:4]


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
    entries = list(transcript_entries)
    batch = _format_transcript_batch(entries, limit=transcript_limit)
    if not batch:
        return {
            "profile_items": [],
            "states": [],
            "relations": [],
            "inferred_relations": [],
            "typed_entities": [],
            "temporal_events": [],
            "continuity_summary": "",
            "decisions": [],
            "batch_text": "",
            "_meta": {
                "json_parse_status": "empty_batch",
                "parse_context": "",
            },
        }

    messages = [
        {
            "role": "system",
            "content": (
                "You extract durable memory from multilingual Hermes chat transcripts.\n"
                "Return one compact JSON object only. Do not use markdown fences, explanations, or trailing text.\n"
                "Schema:\n"
                "{\n"
                '  "profile_items": [{"category":"identity|preference|shared_work","content":"...","slot":"optional-stable-slot","confidence":0.0}],\n'
                '  "states": [{"subject":"...","attribute":"...","value":"...","supersede":true,"confidence":0.0}],\n'
                '  "relations": [{"subject":"...","predicate":"...","object":"...","confidence":0.0}],\n'
                '  "inferred_relations": [{"subject":"...","predicate":"...","object":"...","confidence":0.0,"reason":"short evidence"}],\n'
                '  "typed_entities": [{"turn_number":0,"name":"specific short label","entity_type":"snake_case_type","subject":"User","attributes":{"metric_key":"value"},"confidence":0.0}],\n'
                '  "temporal_events": [{"turn_number":0,"content":"standalone factual event summary","confidence":0.0}],\n'
                '  "continuity_summary": "short durable summary or empty string",\n'
                '  "decisions": ["durable decision", "..."]\n'
                "}\n"
                "Rules:\n"
                "- prefer durable user facts and current project context\n"
                "- ignore markdown tables, quoted transcript dumps, code, wrappers, and assistant policy chatter\n"
                "- keep the JSON compact; prefer the fewest useful items rather than broad coverage\n"
                "- hard caps: profile_items<=3, states<=2, relations<=1, inferred_relations<=1, typed_entities<=4, temporal_events<=4, decisions<=2\n"
                "- keep content values short and factual; target <=12 words for each content/reason/decision string; if unsure, emit [] or \"\" instead of extra explanation\n"
                "- use stable slots only when a profile fact has one obvious durable owner, such as identity:name\n"
                "- use explicit entity names when clear, otherwise use User\n"
                "- inferred_relations are optional; include them only when a relation is strongly implied by multiple transcript cues or stable shared context\n"
                "- keep inferred_relations bounded and conservative; omit weak guesses\n"
                "- typed_entities are optional; use them only for durable user-owned real-world events, purchases, repeated activities, or routines that would support later aggregate queries\n"
                "- when emitting typed_entities, keep attributes compact and scalar; prefer reusable keys like distance_miles, amount_usd, duration_days, count, destination, or category over prose\n"
                "- do not replace temporal_events with typed_entities; when both help, emit both compactly\n"
                "- each typed_entity must reference a real turn_number from the provided batch\n"
                "- temporal_events are optional; include only concrete user events/activities that would help later ordering across time\n"
                "- if the user references a concrete prior trip, visit, road trip, return, start, completion, purchase, or other real-world event as context inside a broader request, include that event when it would help future timeline recall\n"
                "- when many possible temporal_events compete, prefer concrete real-world experiences, visits, trips, returns, starts, completions, and explicit plans over generic information-seeking or topic-shift events\n"
                "- each temporal_event must reference a real turn_number from the provided batch and its content must be a standalone factual summary of that event\n"
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
    selected_entries = [row for row in entries if _normalize_text(row.get("content"))][-transcript_limit:]
    turn_numbers: List[int] = []
    for row in selected_entries:
        try:
            turn_number = int(row.get("turn_number") or 0)
        except (TypeError, ValueError):
            turn_number = 0
        if turn_number > 0:
            turn_numbers.append(turn_number)
    parse_context = f"turns={turn_numbers}" if turn_numbers else ""
    raw_text = _extract_text_content(response)
    payload, parse_status = _extract_json_object_with_status(raw_text, context=parse_context)
    return {
        "profile_items": _normalize_profile_items(payload.get("profile_items")),
        "states": _normalize_states(payload.get("states")),
        "relations": _normalize_relations(payload.get("relations")),
        "inferred_relations": _normalize_inferred_relations(payload.get("inferred_relations")),
        "typed_entities": _normalize_typed_entities(
            payload.get("typed_entities"),
            transcript_entries=entries,
        ),
        "temporal_events": _normalize_temporal_events(
            payload.get("temporal_events"),
            transcript_entries=entries,
        ),
        "continuity_summary": _normalize_text(payload.get("continuity_summary")),
        "decisions": _normalize_decisions(payload.get("decisions")),
        "batch_text": batch,
        "_meta": {
            "json_parse_status": parse_status,
            "parse_context": parse_context,
            "raw_payload_preview": str(raw_text or "")[:240],
            "raw_payload_tail": str(raw_text or "")[-240:],
            "raw_payload_length": len(str(raw_text or "")),
        },
    }
