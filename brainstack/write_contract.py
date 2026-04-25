from __future__ import annotations

import hashlib
from typing import Any, Dict


WRITE_CONTRACT_TRACE_SCHEMA_VERSION = "brainstack.write_contract_trace.v1"
SUPPORTED_WRITE_LANES = {
    "profile",
    "operating",
    "task",
    "continuity",
    "graph",
    "corpus",
}


def _compact(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _stable_hash(value: Any) -> str:
    normalized = _compact(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16] if normalized else ""


def build_write_decision_trace(
    *,
    lane: str,
    accepted: bool,
    reason_code: str,
    source_role: str = "",
    authority_class: str = "",
    canonical: bool = False,
    source_present: bool = True,
    stable_key: str = "",
) -> Dict[str, Any]:
    requested_lane = _compact(lane)
    normalized_lane = requested_lane if requested_lane in SUPPORTED_WRITE_LANES else "unsupported"
    return {
        "schema": WRITE_CONTRACT_TRACE_SCHEMA_VERSION,
        "lane": normalized_lane,
        "requested_lane": requested_lane,
        "accepted": bool(accepted),
        "reason_code": _compact(reason_code) or "unspecified",
        "source_role": _compact(source_role),
        "authority_class": _compact(authority_class),
        "canonical": bool(canonical),
        "source_present": bool(source_present),
        "stable_key_hash": _stable_hash(stable_key),
    }
