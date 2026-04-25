"""Brainstack model-tool schema declarations.

This module keeps the provider's public tool surface as explicit data. It does
not execute tools, infer intent, or make approval/runtime decisions.
"""

from __future__ import annotations

from typing import Any, Dict, List


TASK_STATUS_VALUES = ["pending", "in_progress", "blocked", "completed", "failed", "stale", "cancelled"]


def recall_tool_schema() -> Dict[str, Any]:
    return {
        "name": "brainstack_recall",
        "description": (
            "Recall scoped Brainstack memory evidence for a query. "
            "Read-only; use final_packet.preview as the primary answer source. "
            "Selected evidence is diagnostic support and cannot prove current assignment unless explicitly flagged."
        ),
        "x_brainstack_tool_class": "read_only_memory",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    }


def inspect_tool_schema() -> Dict[str, Any]:
    return {
        "name": "brainstack_inspect",
        "description": (
            "Inspect Brainstack retrieval for a query with channels, routing, selected evidence, "
            "suppressed evidence, and final packet metadata. Read-only."
        ),
        "x_brainstack_tool_class": "read_only_memory_diagnostics",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    }


def stats_tool_schema() -> Dict[str, Any]:
    return {
        "name": "brainstack_stats",
        "description": (
            "Return scoped Brainstack memory-kernel health, row counts, and capability status. "
            "Read-only; does not run repair or mutation."
        ),
        "x_brainstack_tool_class": "read_only_memory_health",
        "parameters": {
            "type": "object",
            "properties": {
                "strict": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    }


def runtime_handoff_update_tool_schema() -> Dict[str, Any]:
    return {
        "name": "runtime_handoff_update",
        "description": (
            "Record the typed runtime status of a pending session-start handoff task. "
            "Use only with a task_id from the runtime handoff block."
        ),
        "x_brainstack_tool_class": "runtime_status_write",
        "x_brainstack_model_callable": False,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": TASK_STATUS_VALUES,
                },
                "result_summary": {"type": "string"},
                "note": {"type": "string"},
                "artifact_refs": {"type": "array", "items": {"type": "string"}},
                "approved_by": {"type": "string"},
            },
            "required": ["task_id", "status"],
        },
    }


def workstream_recap_tool_schema(
    *,
    owner_user_project: str,
    owner_agent_assignment: str,
    source_explicit: str,
    source_manual_migration: str,
) -> Dict[str, Any]:
    return {
        "name": "brainstack_workstream_recap",
        "description": (
            "Commit an explicit, scoped workstream recap summary into Brainstack operating truth. "
            "Requires a typed workstream_id; does not infer workstream identity from prose."
        ),
        "x_brainstack_tool_class": "explicit_workstream_recap_write",
        "x_brainstack_capture_schema": "brainstack.workstream_recap_capture.v1",
        "parameters": {
            "type": "object",
            "properties": {
                "workstream_id": {"type": "string"},
                "summary": {"type": "string"},
                "source_role": {"type": "string", "enum": ["user"]},
                "owner_role": {
                    "type": "string",
                    "enum": [owner_user_project, owner_agent_assignment],
                },
                "source_kind": {
                    "type": "string",
                    "enum": [source_explicit, source_manual_migration],
                },
                "source": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["workstream_id", "summary", "source_role", "owner_role", "source_kind"],
            "additionalProperties": False,
        },
    }


def explicit_capture_tool_schema(*, name: str, operation: str, capture_schema_version: str) -> Dict[str, Any]:
    properties: Dict[str, Any] = {
        "shelf": {"type": "string", "enum": ["profile", "operating", "task"]},
        "stable_key": {"type": "string"},
        "source_role": {"type": "string", "enum": ["user"]},
        "authority_class": {"type": "string"},
        "content": {"type": "string"},
        "category": {"type": "string"},
        "record_type": {"type": "string"},
        "title": {"type": "string"},
        "due_date": {"type": "string"},
        "date_scope": {"type": "string"},
        "status": {"type": "string"},
        "optional": {"type": "boolean"},
        "confidence": {"type": "number"},
        "metadata": {"type": "object"},
    }
    if operation == "supersede":
        properties["supersedes_stable_key"] = {"type": "string"}
    return {
        "name": name,
        "description": (
            "Commit explicit typed Brainstack memory through the durable capture contract. "
            "This tool requires schema fields and does not infer memory intent from prose."
        ),
        "x_brainstack_tool_class": "explicit_memory_write",
        "x_brainstack_capture_schema": capture_schema_version,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": ["shelf", "stable_key", "source_role"],
            "additionalProperties": False,
        },
    }


def consolidate_tool_schema(
    *,
    maintenance_schema_version: str,
    maintenance_class_semantic_index: str,
) -> Dict[str, Any]:
    return {
        "name": "brainstack_consolidate",
        "description": (
            "Run bounded Brainstack memory maintenance. Dry-run by default; apply mode is limited "
            "to derived semantic index rebuild and does not delete durable truth."
        ),
        "x_brainstack_tool_class": "bounded_memory_maintenance",
        "x_brainstack_maintenance_schema": maintenance_schema_version,
        "parameters": {
            "type": "object",
            "properties": {
                "apply": {"type": "boolean"},
                "maintenance_class": {
                    "type": "string",
                    "enum": [maintenance_class_semantic_index],
                },
            },
            "additionalProperties": False,
        },
    }


def build_tool_schemas(
    *,
    capture_schema_version: str,
    maintenance_schema_version: str,
    maintenance_class_semantic_index: str,
    owner_user_project: str,
    owner_agent_assignment: str,
    source_explicit: str,
    source_manual_migration: str,
    runtime_handoff_update_model_callable: bool,
) -> List[Dict[str, Any]]:
    schemas = [
        recall_tool_schema(),
        inspect_tool_schema(),
        stats_tool_schema(),
        explicit_capture_tool_schema(
            name="brainstack_remember",
            operation="remember",
            capture_schema_version=capture_schema_version,
        ),
        explicit_capture_tool_schema(
            name="brainstack_supersede",
            operation="supersede",
            capture_schema_version=capture_schema_version,
        ),
        workstream_recap_tool_schema(
            owner_user_project=owner_user_project,
            owner_agent_assignment=owner_agent_assignment,
            source_explicit=source_explicit,
            source_manual_migration=source_manual_migration,
        ),
        consolidate_tool_schema(
            maintenance_schema_version=maintenance_schema_version,
            maintenance_class_semantic_index=maintenance_class_semantic_index,
        ),
    ]
    if runtime_handoff_update_model_callable:
        schema = runtime_handoff_update_tool_schema()
        schema["x_brainstack_model_callable"] = True
        schemas.append(schema)
    return schemas
