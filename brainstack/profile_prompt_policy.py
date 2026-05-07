from __future__ import annotations

from typing import Any, Mapping

from .profile_contract import logical_profile_slot_from_row, normalize_profile_slot
from .style_contract import STYLE_CONTRACT_SLOT


STYLE_AUTHORITY_RESIDUE_SLOTS = {
    STYLE_CONTRACT_SLOT,
}

BEHAVIOR_PROFILE_SOURCE_CATEGORIES = {
    "communication_style",
    "operating_preference",
    "style_contract",
    "style_preference",
}

DEMOTABLE_BEHAVIOR_PROFILE_SOURCE_CATEGORIES = {
    "communication_style",
    "style_preference",
}

BEHAVIOR_PROFILE_SOURCE_SLOTS = {
    STYLE_CONTRACT_SLOT,
    "preference:addressing",
    "preference:assistant_address_name",
    "preference:communication_style",
    "preference:formatting",
    "preference:verbosity",
}

DEMOTABLE_BEHAVIOR_PROFILE_SOURCE_SLOTS = BEHAVIOR_PROFILE_SOURCE_SLOTS - {STYLE_CONTRACT_SLOT}


def profile_prompt_source_key(row: Mapping[str, Any]) -> str:
    key = str(row.get("logical_stable_key") or "").strip()
    if not key:
        key = str(logical_profile_slot_from_row(row) or "").strip()
    if not key:
        key = str(row.get("stable_key") or row.get("storage_key") or "").strip()
    return key.split("::principal_scope::", 1)[0].strip()


def profile_source_candidate_keys(row: Mapping[str, Any]) -> set[str]:
    logical_key = normalize_profile_slot(str(logical_profile_slot_from_row(row) or "")).strip()
    stored_key = normalize_profile_slot(str(row.get("stable_key") or "")).strip()
    storage_key = normalize_profile_slot(
        str(row.get("storage_key") or "").split("::principal_scope::", 1)[0]
    ).strip()
    return {key for key in (logical_key, stored_key, storage_key) if key}


def is_behavior_profile_source_item(row: Mapping[str, Any]) -> bool:
    category = normalize_profile_slot(str(row.get("category") or "")).strip()
    candidate_keys = profile_source_candidate_keys(row)
    if candidate_keys & STYLE_AUTHORITY_RESIDUE_SLOTS:
        return True
    if category in BEHAVIOR_PROFILE_SOURCE_CATEGORIES:
        return True
    if category == "preference" and candidate_keys & BEHAVIOR_PROFILE_SOURCE_SLOTS:
        return True
    return False


def is_demotable_behavior_profile_source_item(row: Mapping[str, Any]) -> bool:
    category = normalize_profile_slot(str(row.get("category") or "")).strip()
    candidate_keys = profile_source_candidate_keys(row)
    if candidate_keys & STYLE_AUTHORITY_RESIDUE_SLOTS:
        return False
    if category in DEMOTABLE_BEHAVIOR_PROFILE_SOURCE_CATEGORIES:
        return True
    if category == "preference" and candidate_keys & DEMOTABLE_BEHAVIOR_PROFILE_SOURCE_SLOTS:
        return True
    return False
