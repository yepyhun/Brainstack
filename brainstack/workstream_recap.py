from __future__ import annotations

from typing import Any, Dict, Mapping

from .operating_truth import (
    OPERATING_RECORD_ACTIVE_WORK,
    OPERATING_RECORD_CURRENT_COMMITMENT,
    OPERATING_RECORD_NEXT_STEP,
    OPERATING_RECORD_OPEN_DECISION,
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
    recent_work_authority_rank,
)


WORKSTREAM_RECAP_SCHEMA = "brainstack.workstream_recap.v1"

WORKSTREAM_RECAP_ANCHOR_RECORD_TYPES = {
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
    OPERATING_RECORD_ACTIVE_WORK,
    OPERATING_RECORD_CURRENT_COMMITMENT,
    OPERATING_RECORD_NEXT_STEP,
    OPERATING_RECORD_OPEN_DECISION,
}

WORKSTREAM_RECAP_CONTINUITY_SUPPORT_KINDS = {
    "tier2_summary",
    "session_summary",
}


def _metadata(row: Mapping[str, Any]) -> Dict[str, Any]:
    raw_metadata = row.get("metadata")
    return dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}


def _workstream_id(row: Mapping[str, Any]) -> str:
    metadata = _metadata(row)
    return str(metadata.get("workstream_id") or row.get("workstream_id") or "").strip()


def is_workstream_recap_anchor(row: Mapping[str, Any]) -> bool:
    record_type = str(row.get("record_type") or "").strip()
    if record_type not in WORKSTREAM_RECAP_ANCHOR_RECORD_TYPES:
        return False
    if not _workstream_id(row):
        return False
    if record_type == OPERATING_RECORD_RECENT_WORK_SUMMARY and recent_work_authority_rank(dict(row)) < 200:
        return False
    return True


def workstream_recap_flags(*, shelf: str, row: Mapping[str, Any]) -> Dict[str, Any]:
    """Return type/metadata-derived recap flags without looking at query wording."""
    shelf_name = str(shelf or "").strip()
    record_type = str(row.get("record_type") or "").strip()
    kind = str(row.get("kind") or "").strip()
    workstream_id = _workstream_id(row)

    if shelf_name == "operating" and is_workstream_recap_anchor(row):
        return {
            "schema": WORKSTREAM_RECAP_SCHEMA,
            "workstream_id": workstream_id,
            "recap_surface": True,
            "supporting_evidence_only": False,
            "reason": "scoped_workstream_recap_anchor",
        }

    if shelf_name == "operating" and record_type in WORKSTREAM_RECAP_ANCHOR_RECORD_TYPES:
        return {
            "schema": WORKSTREAM_RECAP_SCHEMA,
            "workstream_id": workstream_id,
            "recap_surface": False,
            "supporting_evidence_only": True,
            "reason": "supporting_only_unscoped_operating_recap",
        }

    if shelf_name in {"continuity_match", "continuity_recent"} and kind in WORKSTREAM_RECAP_CONTINUITY_SUPPORT_KINDS:
        return {
            "schema": WORKSTREAM_RECAP_SCHEMA,
            "workstream_id": workstream_id,
            "recap_surface": False,
            "supporting_evidence_only": not bool(workstream_id),
            "reason": (
                "supporting_only_unscoped_tier2_summary"
                if not workstream_id
                else "scoped_continuity_recap_support"
            ),
        }

    return {
        "schema": WORKSTREAM_RECAP_SCHEMA,
        "workstream_id": workstream_id,
        "recap_surface": False,
        "supporting_evidence_only": False,
        "reason": "",
    }


def annotate_workstream_recap_row(row: Dict[str, Any], *, shelf: str) -> Dict[str, Any]:
    flags = workstream_recap_flags(shelf=shelf, row=row)
    row["_brainstack_workstream_recap_schema"] = flags["schema"]
    row["_brainstack_workstream_id"] = flags["workstream_id"]
    row["_brainstack_recap_surface"] = bool(flags["recap_surface"])
    row["_brainstack_supporting_evidence_only"] = bool(flags["supporting_evidence_only"])
    row["_brainstack_workstream_recap_reason"] = str(flags["reason"] or "")
    return row

