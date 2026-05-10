from __future__ import annotations

from typing import Any, Mapping

from .scope_identity import build_memory_scope_identity


MULTI_PROFILE_SUPPORT_SCHEMA = "brainstack.multi_profile_shared_backend.v1"
MEMORY_CONFLICT_PRIMITIVE_SCHEMA = "brainstack.memory_conflict_primitive.v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def profile_scope_from_kwargs(**kwargs: Any) -> dict[str, Any]:
    return build_memory_scope_identity(**kwargs)


def _profile_identity_present(scope: Mapping[str, Any]) -> bool:
    return bool(_text(scope.get("agent_identity")) or _text(scope.get("agent_workspace")))


def build_multi_profile_support_verdict(
    *,
    profile_scopes: list[Mapping[str, Any]],
    shelf_results: Mapping[str, bool],
) -> dict[str, Any]:
    degraded_reasons: list[str] = []
    scope_keys = [_text(scope.get("principal_scope_key")) for scope in profile_scopes]
    if not profile_scopes:
        degraded_reasons.append("no_profile_scopes")
    if any(not _profile_identity_present(scope) for scope in profile_scopes):
        degraded_reasons.append("missing_profile_identity")
    if len([key for key in scope_keys if key]) != len(set(key for key in scope_keys if key)):
        degraded_reasons.append("profile_scope_collision")
    missing_shelves = sorted(key for key, passed in shelf_results.items() if passed is not True)
    if missing_shelves:
        degraded_reasons.append("shelf_isolation_not_proven")
    status = "certified" if not degraded_reasons else "degraded"
    return {
        "schema": MULTI_PROFILE_SUPPORT_SCHEMA,
        "status": status,
        "scope_identity_source": "principal_scope_key",
        "profile_identity_present": not any(not _profile_identity_present(scope) for scope in profile_scopes),
        "shared_scope_policy": "none_by_default_explicit_named_scope_only",
        "profile_count": len(profile_scopes),
        "distinct_principal_scope_count": len(set(key for key in scope_keys if key)),
        "certified_shelves": sorted(key for key, passed in shelf_results.items() if passed is True),
        "degraded_reasons": degraded_reasons,
        "raw_private_scope_values_in_verdict": False,
    }


def build_memory_conflict_primitive(
    *,
    subject: str,
    slot: str,
    competing_claim_refs: list[str],
    source_scope_refs: list[str],
    receipt_refs: list[str],
    status: str = "open",
    resolution_requirement: str = "explicit_trusted_resolution",
) -> dict[str, Any]:
    return {
        "schema": MEMORY_CONFLICT_PRIMITIVE_SCHEMA,
        "subject": _text(subject),
        "slot": _text(slot),
        "competing_claim_refs": [_text(item) for item in competing_claim_refs if _text(item)],
        "source_scope_ref_count": len([item for item in source_scope_refs if _text(item)]),
        "receipt_refs": [_text(item) for item in receipt_refs if _text(item)],
        "status": _text(status) or "open",
        "resolution_requirement": _text(resolution_requirement) or "explicit_trusted_resolution",
        "current_truth_allowed": False,
        "agent_facing": True,
    }
