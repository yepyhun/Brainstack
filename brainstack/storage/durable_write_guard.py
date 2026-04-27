from __future__ import annotations

from typing import Any, Mapping

from ..core.admission import CURRENT_ASSIGNMENT_AUTHORITIES, SupportVisibility


class DurableTruthWriteViolation(ValueError):
    """Raised when a durable truth write bypasses the required permit boundary."""


_DERIVED_SOURCE_PREFIXES = (
    "tier2:",
    "consolidation:",
    "session_recap:",
    "pulse:",
    "background:",
)

_DERIVED_AUTHORITIES = {
    "tier2_summary",
    "pulse_background",
    "session_recap",
    "assistant_claim",
    "assistant_self_claim",
    "graph_inference",
    "transcript_event",
    "runtime_diagnostic",
}

_SUPPORT_ONLY_VISIBILITIES = {
    SupportVisibility.HISTORY_ONLY.value,
    SupportVisibility.CONTRADICTION_ONLY.value,
    SupportVisibility.INSPECT_ONLY.value,
}


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _casefold(value: Any) -> str:
    return _text(value).casefold()


def _slot_key(value: Any) -> str:
    return _casefold(value).replace(":", ".")


def _has_permit(metadata: Mapping[str, Any]) -> bool:
    permit = _as_mapping(metadata.get("truth_write_permit"))
    context = _as_mapping(metadata.get("durable_write_context"))
    permit_id = _text(permit.get("permit_id") or context.get("permit_id"))
    write_path_class = _text(permit.get("write_path_class") or context.get("write_path_class"))
    source_authority = _text(permit.get("source_authority") or context.get("source_authority"))
    return bool(permit_id and write_path_class and source_authority)


def _has_admission(metadata: Mapping[str, Any]) -> bool:
    admission = _as_mapping(metadata.get("admission"))
    return bool(
        admission.get("policy_version")
        and admission.get("decision")
        and admission.get("claim_id")
    )


def _has_trusted_context(metadata: Mapping[str, Any]) -> bool:
    context = _as_mapping(metadata.get("durable_write_context"))
    permit = _as_mapping(metadata.get("truth_write_permit"))
    return bool(
        context.get("trusted_context_id")
        or context.get("migration_id")
        or context.get("operator_action_id")
        or context.get("canary_run_id")
        or permit.get("trusted_context_id")
        or permit.get("migration_id")
        or permit.get("operator_action_id")
        or permit.get("canary_run_id")
    )


def _source_authority(metadata: Mapping[str, Any]) -> str:
    context = _as_mapping(metadata.get("durable_write_context"))
    permit = _as_mapping(metadata.get("truth_write_permit"))
    admission = _as_mapping(metadata.get("admission"))
    return _casefold(
        context.get("source_authority")
        or permit.get("source_authority")
        or metadata.get("source_authority")
        or admission.get("authority_class")
    )


def _is_derived_source(source: str, metadata: Mapping[str, Any]) -> bool:
    normalized_source = _casefold(source)
    if any(normalized_source.startswith(prefix) for prefix in _DERIVED_SOURCE_PREFIXES):
        return True
    authority = _source_authority(metadata)
    if authority in _DERIVED_AUTHORITIES:
        return True
    provenance = _as_mapping(metadata.get("provenance"))
    origin = _casefold(metadata.get("origin") or provenance.get("origin") or provenance.get("tier"))
    return origin in {"tier2", "background", "session_recap", "pulse"}


def _force_support_only_invariants(metadata: dict[str, Any]) -> None:
    admission = _as_mapping(metadata.get("admission"))
    visibility = _casefold(metadata.get("support_visibility") or admission.get("support_visibility"))
    if visibility not in _SUPPORT_ONLY_VISIBILITIES:
        return
    metadata["truth_eligible"] = False
    metadata["model_facing_default"] = False
    metadata.setdefault("max_claim_strength", "none")
    if isinstance(metadata.get("admission"), dict):
        metadata["admission"]["truth_eligible"] = False


def _current_assignment_authority(metadata: Mapping[str, Any], *, shelf: str, record_type: str = "") -> bool:
    if bool(metadata.get("current_assignment_authority")):
        return True
    if _casefold(record_type) == "current_assignment_state":
        return True
    if _casefold(shelf) == "task" and bool(metadata.get("current_assignment_authority")):
        return True
    return False


def guard_and_normalize_durable_truth_metadata(
    *,
    shelf: str,
    source: str,
    metadata: Mapping[str, Any] | None,
    record_type: str = "",
    slot: str = "",
) -> dict[str, Any]:
    normalized = dict(metadata or {})
    _force_support_only_invariants(normalized)

    is_current_assignment = _current_assignment_authority(normalized, shelf=shelf, record_type=record_type)

    if _is_derived_source(source, normalized) and not (_has_permit(normalized) or _has_admission(normalized)):
        if _casefold(shelf) in {"operating", "task"} and not is_current_assignment:
            return normalized
        raise DurableTruthWriteViolation(
            f"Derived durable {shelf} write requires TruthWritePermit or admission metadata"
        )

    permit = _as_mapping(normalized.get("truth_write_permit"))
    if permit and not _has_permit(normalized):
        raise DurableTruthWriteViolation(f"Invalid TruthWritePermit for durable {shelf} write")

    if is_current_assignment:
        authority = _source_authority(normalized)
        if authority and authority not in {item.value for item in CURRENT_ASSIGNMENT_AUTHORITIES}:
            raise DurableTruthWriteViolation(
                f"Current assignment {shelf} write requires explicit user/host/operator authority"
            )

    if permit and _casefold(shelf) not in {str(item).casefold() for item in permit.get("allowed_shelves", [])}:
        raise DurableTruthWriteViolation(f"TruthWritePermit does not allow {shelf} shelf")

    allowed_slots = permit.get("allowed_slots") if isinstance(permit, Mapping) else None
    if (
        slot
        and isinstance(allowed_slots, list)
        and allowed_slots
        and _slot_key(slot) not in {_slot_key(item) for item in allowed_slots}
    ):
        raise DurableTruthWriteViolation(f"TruthWritePermit does not allow slot {slot}")

    return normalized
