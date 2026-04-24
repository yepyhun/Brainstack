from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping


PRINCIPAL_SCOPE_KEY_FIELDS = (
    "platform",
    "user_id",
    "agent_identity",
    "agent_workspace",
    "chat_type",
    "chat_id",
    "thread_id",
)
PERSONAL_SCOPE_KEY_FIELDS = ("platform", "user_id")
DISPLAY_SCOPE_FIELDS = ("chat_name",)
TRANSIENT_SCOPE_FIELDS = (
    "session_id",
    "container_id",
    "connection_id",
    "process_id",
    "pid",
    "execution_thread_id",
    "runtime_thread_id",
)


def normalized_scope_value(value: Any) -> str:
    return str(value or "").strip()


def scope_key_from_payload(payload: Mapping[str, Any] | None, *, fields: Iterable[str]) -> str:
    if not isinstance(payload, Mapping):
        return ""
    parts: list[str] = []
    for key in fields:
        value = normalized_scope_value(payload.get(key))
        if value:
            parts.append(f"{key}:{value}")
    return "|".join(parts)


def scope_payload_from_key(scope_key: str) -> Dict[str, str]:
    payload: Dict[str, str] = {}
    for raw_part in str(scope_key or "").split("|"):
        part = normalized_scope_value(raw_part)
        if not part or ":" not in part:
            continue
        key, value = part.split(":", 1)
        normalized_key = normalized_scope_value(key)
        normalized_value = normalized_scope_value(value)
        if normalized_key and normalized_value:
            payload[normalized_key] = normalized_value
    return payload


def personal_scope_key_from_payload(payload: Mapping[str, Any] | None) -> str:
    return scope_key_from_payload(payload, fields=PERSONAL_SCOPE_KEY_FIELDS)


def principal_scope_key_from_payload(payload: Mapping[str, Any] | None) -> str:
    return scope_key_from_payload(payload, fields=PRINCIPAL_SCOPE_KEY_FIELDS)


def build_memory_scope_identity(**kwargs: Any) -> Dict[str, Any]:
    """Build Brainstack's Hindsight-style stable bank identity.

    The key intentionally uses durable user/chat/workspace metadata and records
    transient runtime ids as ignored diagnostics instead of durable identity.
    """

    user_id = normalized_scope_value(kwargs.get("user_id"))
    if not user_id:
        return {}

    scope: Dict[str, Any] = {"user_id": user_id}
    for key in PRINCIPAL_SCOPE_KEY_FIELDS:
        if key == "user_id":
            continue
        value = normalized_scope_value(kwargs.get(key))
        if value:
            scope[key] = value
    for key in DISPLAY_SCOPE_FIELDS:
        value = normalized_scope_value(kwargs.get(key))
        if value:
            scope[key] = value

    personal_scope_key = personal_scope_key_from_payload(scope)
    if personal_scope_key:
        scope["personal_scope_key"] = personal_scope_key
    principal_scope_key = principal_scope_key_from_payload(scope)
    if principal_scope_key:
        scope["principal_scope_key"] = principal_scope_key
        scope["memory_bank_identity"] = principal_scope_key
        scope["memory_bank_identity_source"] = "principal_scope_key"

    ignored = {
        key: normalized_scope_value(kwargs.get(key))
        for key in TRANSIENT_SCOPE_FIELDS
        if normalized_scope_value(kwargs.get(key))
    }
    if ignored:
        scope["transient_scope_fields_ignored"] = ignored
    return scope
