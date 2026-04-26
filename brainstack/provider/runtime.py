# ruff: noqa: F401
"""Brainstack memory plugin — continuity, profile, graph-truth, and corpus substrate.

Current provider slice:
- continuity shelf for recent turns, session snapshots, and active work state
- transcript shelf for append-only raw turns and bounded session snapshots
- separate profile shelf for durable identity, preference, and shared-work anchors
- hook-based recall/write path with no model-facing tools by default
- graph-truth shelf for entities, relations, temporal state, supersession, and conflicts
- corpus shelf for explicit documents, section-aware recall, and bounded packing
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Dict, List, Mapping, Sequence

try:
    from agent.memory_provider import MemoryProvider
except ModuleNotFoundError as exc:
    if exc.name not in {"agent", "agent.memory_provider"}:
        raise

    class MemoryProvider:  # type: ignore[no-redef]
        """Fallback base for importing Brainstack contracts outside Hermes."""

        pass

from ..control_plane import build_working_memory_packet
from ..consolidation import build_consolidation_source
from ..db import BrainstackStore
from ..donors import continuity_adapter, corpus_adapter, graph_adapter
from ..donors.registry import get_donor_registry
from ..explicit_capture import (
    EXPLICIT_CAPTURE_SCHEMA_VERSION,
    build_commit_metadata,
    receipt_excerpt,
    validate_explicit_capture_payload,
)
from ..explicit_truth_parity import build_explicit_truth_parity, derive_host_trace_id
from ..extraction_pipeline import build_session_message_ingest_plan, build_turn_ingest_plan
from ..maintenance import (
    MAINTENANCE_CLASS_SEMANTIC_INDEX,
    MAINTENANCE_SCHEMA_VERSION,
    normalize_maintenance_args,
    run_bounded_maintenance,
)
from ..operating_truth import (
    OPERATING_OWNER,
    OPERATING_RECORD_CANONICAL_POLICY,
    OPERATING_RECORD_OPEN_DECISION,
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
    OPERATING_RECORD_RUNTIME_APPROVAL_POLICY,
    RECENT_WORK_AUTHORITY_CANONICAL,
    RECENT_WORK_OWNER_AGENT_ASSIGNMENT,
    RECENT_WORK_OWNER_USER_PROJECT,
    RECENT_WORK_SOURCE_EXPLICIT,
    RECENT_WORK_SOURCE_MANUAL_MIGRATION,
    build_operating_stable_key,
    normalize_recent_work_metadata,
    parse_operating_capture,
    recent_work_stable_key,
    should_promote_open_decision,
)
from ..output_contract import validate_output_against_contract
from ..provider_diagnostics import (
    build_provider_lifecycle_status,
    build_provider_memory_kernel_doctor,
    build_provider_query_inspect,
    handle_brainstack_inspect,
    handle_brainstack_recall,
    handle_brainstack_stats,
)
from ..profile_contract import (
    NATIVE_EXPLICIT_PROFILE_METADATA_KEY,
    NATIVE_EXPLICIT_PROFILE_MIRROR_SOURCE,
)
from ..reconciler import reconcile_tier2_candidates
from ..retrieval import (
    build_compression_hint,
    build_system_prompt_projection,
)
from ..style_contract import (
    apply_style_contract_patch,
    build_style_contract_from_text,
    has_explicit_style_authority_signal,
    list_style_contract_rules,
    looks_like_style_contract_fragment,
    looks_like_style_contract_teaching,
)
from ..structured_understanding import resolve_user_timezone
from ..scope_identity import build_memory_scope_identity
from ..task_memory import build_task_stable_key, parse_task_capture
from ..tier2_extractor import extract_tier2_candidates
from ..tool_schemas import (
    build_tool_schemas,
    explicit_capture_tool_schema,
    runtime_handoff_update_tool_schema,
    workstream_recap_tool_schema,
)
from ..transcript import trim_text_boundary
from ..runtime_handoff_io import (
    ACTIVE_TASK_STATUSES,
    ALL_TASK_STATUSES,
    TERMINAL_TASK_STATUSES,
    locate_task_record,
    summarize_runtime_handoff_dirs,
    utc_now_iso,
    write_task_record,
)

logger = logging.getLogger(__name__)

DISABLED_MEMORY_WRITE_TOOLS = {
    "brainstack_invalidate",
}


def _normalize_compact_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())

def _stable_native_write_id(*, action: str, target: str, content: str) -> str:
    normalized = " ".join(str(content or "").split())
    digest = hashlib.sha256(f"{action}|{target}|{normalized}".encode("utf-8")).hexdigest()[:16]
    return f"native:{action}:{target}:{digest}"


def _native_profile_mirror_payload(*, native_write_id: str, action: str, target: str) -> Dict[str, Any]:
    return {
        "native_write_id": native_write_id,
        "source_generation": native_write_id,
        "mirrored_from": NATIVE_EXPLICIT_PROFILE_MIRROR_SOURCE,
        "native_action": action,
        "native_target": target,
    }


_NATIVE_EXPLICIT_ENTRY_SPLIT = re.compile(r"\n\s*§\s*\n|\n+")


def _iter_native_explicit_entries(content: str) -> List[str]:
    return [
        " ".join(part.strip().split())
        for part in _NATIVE_EXPLICIT_ENTRY_SPLIT.split(str(content or ""))
        if str(part or "").strip()
    ]


def _derive_native_profile_mirror_entries(content: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for index, entry in enumerate(_iter_native_explicit_entries(content), start=1):
        stable_digest = hashlib.sha256(entry.encode("utf-8")).hexdigest()[:16]
        entries.append(
            {
                "category": "native_profile_mirror",
                "stable_key": f"native_profile_mirror:{index}:{stable_digest}",
                "content": entry,
                "confidence": 1.0,
                "source": "native_explicit_profile",
            }
        )
    return entries


def _build_personal_scope_key(*, platform: str = "", user_id: str = "") -> str:
    parts: List[str] = []
    normalized_platform = str(platform or "").strip()
    normalized_user_id = str(user_id or "").strip()
    if normalized_platform:
        parts.append(f"platform:{normalized_platform}")
    if normalized_user_id:
        parts.append(f"user_id:{normalized_user_id}")
    return "|".join(parts)


def _extract_heading_titles(block: str) -> List[str]:
    titles: List[str] = []
    for raw_line in str(block or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("#"):
            continue
        titles.append(line)
    return titles


def _load_plugin_config() -> dict:
    from hermes_constants import get_hermes_home

    config_path = get_hermes_home() / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml  # type: ignore[import-untyped]

        with open(config_path, encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        return config.get("plugins", {}).get("brainstack", {}) or {}
    except Exception:
        return {}


def _normalize_path(value: str, hermes_home: str) -> str:
    value = value.replace("$HERMES_HOME", hermes_home)
    value = value.replace("${HERMES_HOME}", hermes_home)
    return str(Path(value).expanduser())


def _debug_row_snapshot(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "session_id": str(row.get("session_id") or ""),
        "turn_number": int(row.get("turn_number") or 0),
        "stable_key": str(row.get("stable_key") or ""),
        "row_type": str(row.get("row_type") or ""),
        "document_id": int(row.get("document_id") or 0),
        "section_index": int(row.get("section_index") or 0),
        "created_at": str(row.get("created_at") or ""),
        "keyword_score": float(row.get("keyword_score") or 0.0),
        "semantic_score": float(row.get("semantic_score") or 0.0),
        "channels": list(row.get("_brainstack_channels") or []),
        "channel_ranks": dict(row.get("_brainstack_channel_ranks") or {}),
        "rrf_score": float(row.get("_brainstack_rrf_score") or 0.0),
        "content_excerpt": str(row.get("content") or "")[:240],
    }


def _build_principal_scope(**kwargs: Any) -> Dict[str, Any]:
    scope = build_memory_scope_identity(**kwargs)
    if not scope:
        return {}
    timezone_name = resolve_user_timezone(kwargs.get("timezone"))
    if timezone_name and timezone_name != "UTC":
        scope["timezone"] = timezone_name
    return scope
