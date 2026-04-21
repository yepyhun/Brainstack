from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping

from .style_contract import STYLE_CONTRACT_SLOT


COMMUNICATION_CANONICAL_SLOTS: frozenset[str] = frozenset()
NATIVE_EXPLICIT_PROFILE_METADATA_KEY = "native_explicit_profile"
NATIVE_EXPLICIT_PROFILE_MIRROR_SOURCE = "native_profile"

def normalize_compare_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def normalize_profile_slot(value: Any) -> str:
    normalized = normalize_compare_text(value).replace(" ", "_")
    normalized = re.sub(r"[^a-z0-9:_-]+", "_", normalized).strip("_")
    return normalized


def _style_contract_payload_has_rules(style_contract: Mapping[str, Any] | None) -> bool:
    if not isinstance(style_contract, Mapping):
        return False
    logical_slot = normalize_profile_slot(
        style_contract.get("slot") or style_contract.get("stable_key") or ""
    )
    metadata = style_contract.get("metadata")
    if logical_slot == "preference:style_contract":
        if isinstance(metadata, Mapping):
            sections = metadata.get("style_contract_sections")
            if isinstance(sections, list) and sections:
                return True
        content = str(style_contract.get("content") or "").strip()
        if content:
            return True
    title = str(style_contract.get("title") or "").strip()
    if title:
        return True
    sections = style_contract.get("sections")
    if not isinstance(sections, list):
        return False
    for section in sections:
        if not isinstance(section, Mapping):
            continue
        lines = section.get("lines")
        if not isinstance(lines, list):
            continue
        if any(str(line or "").strip() for line in lines):
            return True
    return False


def has_style_authority_signal(
    *,
    existing_items: Iterable[Mapping[str, Any]],
    style_contract: Mapping[str, Any] | None = None,
) -> bool:
    if _style_contract_payload_has_rules(style_contract):
        return True
    for item in existing_items:
        logical_key = normalize_profile_slot(
            item.get("slot") or item.get("stable_key") or ""
        )
        if logical_key == STYLE_CONTRACT_SLOT:
            return True
    return False


def native_explicit_profile_payload(row: Mapping[str, Any]) -> Dict[str, Any] | None:
    metadata = row.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    payload = metadata.get(NATIVE_EXPLICIT_PROFILE_METADATA_KEY)
    if not isinstance(payload, Mapping):
        return None
    return {str(key): value for key, value in payload.items()}


def is_native_explicit_profile_item(row: Mapping[str, Any]) -> bool:
    payload = native_explicit_profile_payload(row)
    if not isinstance(payload, Mapping):
        return False
    return str(payload.get("mirrored_from") or "").strip() == NATIVE_EXPLICIT_PROFILE_MIRROR_SOURCE


def is_native_explicit_style_item(row: Mapping[str, Any]) -> bool:
    if not is_native_explicit_profile_item(row):
        return False
    logical_key = normalize_profile_slot(row.get("slot") or row.get("stable_key") or "")
    return logical_key == STYLE_CONTRACT_SLOT


def resolve_direct_identity_profile_slots(query: str) -> tuple[str, ...]:
    del query
    return ()


def expand_communication_profile_items(
    *,
    category: str,
    content: str,
    slot: str,
    confidence: float,
    source: str,
) -> List[Dict[str, Any]]:
    return []


def derive_transcript_communication_profile_items(
    transcript_entries: Iterable[Mapping[str, Any]],
    *,
    existing_items: Iterable[Mapping[str, Any]],
    style_contract: Mapping[str, Any] | None = None,
    source: str = "tier2_transcript_rule",
) -> List[Dict[str, Any]]:
    return []


def derive_transcript_identity_profile_items(
    transcript_entries: Iterable[Mapping[str, Any]],
    *,
    existing_items: Iterable[Mapping[str, Any]],
    source: str = "tier2_transcript_rule",
) -> List[Dict[str, Any]]:
    del transcript_entries, existing_items, source
    return []
