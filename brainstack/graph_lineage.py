from __future__ import annotations

import hashlib
from typing import Any, Mapping


GRAPH_SOURCE_LINEAGE_SCHEMA = "brainstack.graph_source_lineage.v1"

ALLOWED_GRAPH_SOURCE_KINDS = frozenset(
    {
        "explicit_api",
        "typed_evidence",
        "turn",
        "transcript",
        "continuity",
        "corpus_document",
        "document",
        "migration",
        "tier2",
        "unknown",
    }
)

PRIVATE_LINEAGE_FIELD_HINTS = frozenset(
    {
        "content",
        "body",
        "raw_text",
        "text",
        "path",
        "file_path",
        "runtime_path",
        "auth",
        "token",
        "secret",
        "password",
    }
)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _stable_redaction_id(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"redacted:{digest}"


def _looks_private_identifier(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    lowered = text.casefold()
    if text.startswith(("/", "~", "\\\\")):
        return True
    if len(text) >= 3 and text[1] == ":" and text[2] in {"\\", "/"}:
        return True
    return any(marker in lowered for marker in ("/home/", "/users/", "/opt/data/", "auth", "token", "secret", "password"))


def _safe_identifier(value: Any) -> tuple[str, bool]:
    text = _clean_text(value)
    if not text:
        return "", False
    if _looks_private_identifier(text):
        return _stable_redaction_id(text), True
    return text[:160], False


def _source_kind_from_metadata(metadata: Mapping[str, Any], *, source: str) -> str:
    explicit = _clean_text(metadata.get("lineage_source_kind") or metadata.get("source_kind")).lower()
    if explicit in ALLOWED_GRAPH_SOURCE_KINDS:
        return explicit
    if _clean_text(metadata.get("source_turn_id")):
        return "turn"
    if _clean_text(metadata.get("source_document_id")):
        return "document"
    nested = metadata.get("graph_evidence")
    if isinstance(nested, Mapping):
        if _clean_text(nested.get("source_turn_id")):
            return "turn"
        if _clean_text(nested.get("source_document_id")):
            return "document"
        return "typed_evidence"
    normalized_source = _clean_text(source).casefold()
    if normalized_source.startswith("corpus") or normalized_source.startswith("doc:"):
        return "corpus_document"
    if normalized_source.startswith("tier2"):
        return "tier2"
    if normalized_source.startswith("migration:"):
        return "migration"
    if source:
        return "explicit_api"
    return "unknown"


def build_graph_source_lineage(
    *,
    metadata: Mapping[str, Any] | None,
    source: str,
    graph_kind: str,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    existing = payload.get("graph_source_lineage")
    if isinstance(existing, Mapping) and str(existing.get("schema") or "") == GRAPH_SOURCE_LINEAGE_SCHEMA:
        return dict(existing)

    nested_evidence = payload.get("graph_evidence")
    evidence = nested_evidence if isinstance(nested_evidence, Mapping) else {}
    nested_provenance = payload.get("provenance")
    provenance = nested_provenance if isinstance(nested_provenance, Mapping) else {}
    source_ids = provenance.get("source_ids") if isinstance(provenance.get("source_ids"), list) else []

    raw_stable_id = (
        payload.get("lineage_source_id")
        or payload.get("source_stable_id")
        or payload.get("source_turn_id")
        or payload.get("source_document_id")
        or evidence.get("source_turn_id")
        or evidence.get("source_document_id")
        or (source_ids[0] if source_ids else "")
        or source
    )
    source_stable_id, redacted = _safe_identifier(raw_stable_id)
    source_kind = _source_kind_from_metadata(payload, source=source)
    temporal = payload.get("temporal")
    temporal_observed_at = temporal.get("observed_at") if isinstance(temporal, Mapping) else ""
    observed_at = _clean_text(payload.get("observed_at") or temporal_observed_at)
    if not observed_at:
        observed_at = _clean_text(payload.get("created_at") or payload.get("updated_at") or "")
    source_row_table, table_redacted = _safe_identifier(payload.get("source_row_table") or payload.get("lineage_source_table"))
    source_row_id, row_redacted = _safe_identifier(payload.get("source_row_id") or payload.get("lineage_source_row_id"))
    provenance_class = _clean_text(
        payload.get("provenance_class")
        or evidence.get("provenance_class")
        or provenance.get("origin")
        or payload.get("source_kind")
        or source_kind
    )

    status = "active" if source_stable_id and source_kind != "unknown" else "degraded"
    lineage: dict[str, Any] = {
        "schema": GRAPH_SOURCE_LINEAGE_SCHEMA,
        "status": status,
        "source_kind": source_kind if source_kind in ALLOWED_GRAPH_SOURCE_KINDS else "unknown",
        "source_stable_id": source_stable_id,
        "graph_kind": _clean_text(graph_kind),
        "provenance_class": provenance_class,
    }
    if observed_at:
        lineage["observed_at"] = observed_at
    if source_row_table:
        lineage["source_row_table"] = source_row_table
    if source_row_id:
        lineage["source_row_id"] = source_row_id
    if redacted or table_redacted or row_redacted:
        lineage["redacted"] = True
        lineage["redaction_reason"] = "private_identifier"
    if status != "active":
        lineage["degraded_reason"] = "missing_structured_source"
    return {key: value for key, value in lineage.items() if value not in ("", None, [])}


def attach_graph_source_lineage(
    metadata: Mapping[str, Any] | None,
    *,
    source: str,
    graph_kind: str,
) -> dict[str, Any]:
    output = dict(metadata or {})
    lineage = build_graph_source_lineage(metadata=output, source=source, graph_kind=graph_kind)
    output["graph_source_lineage"] = lineage
    provenance = output.get("provenance")
    if isinstance(provenance, Mapping):
        sanitized_provenance = dict(provenance)
        source_ids = sanitized_provenance.get("source_ids")
        if isinstance(source_ids, list):
            sanitized_ids: list[str] = []
            redacted = False
            for source_id in source_ids:
                safe_source_id, was_redacted = _safe_identifier(source_id)
                if safe_source_id:
                    sanitized_ids.append(safe_source_id)
                redacted = redacted or was_redacted
            sanitized_provenance["source_ids"] = sorted(set(sanitized_ids))
            if redacted:
                sanitized_provenance["redacted"] = True
                sanitized_provenance["redaction_reason"] = "private_identifier"
            output["provenance"] = sanitized_provenance
    if lineage.get("status") == "active":
        output.setdefault("graph_authority_status", "trusted_with_lineage")
    else:
        output["graph_authority_status"] = "degraded_missing_lineage"
    for key in list(output):
        if key.casefold() in PRIVATE_LINEAGE_FIELD_HINTS:
            output.pop(key, None)
    return output


def compact_graph_source_lineage(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        return {}
    lineage = metadata.get("graph_source_lineage")
    if not isinstance(lineage, Mapping):
        return {}
    allowed = {
        "schema",
        "status",
        "source_kind",
        "source_stable_id",
        "source_row_table",
        "source_row_id",
        "observed_at",
        "graph_kind",
        "provenance_class",
        "degraded_reason",
        "redacted",
        "redaction_reason",
    }
    return {
        str(key): value
        for key, value in lineage.items()
        if key in allowed and value not in ("", None, [])
    }


__all__ = [
    "ALLOWED_GRAPH_SOURCE_KINDS",
    "GRAPH_SOURCE_LINEAGE_SCHEMA",
    "attach_graph_source_lineage",
    "build_graph_source_lineage",
    "compact_graph_source_lineage",
]
