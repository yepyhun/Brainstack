"""Authority contracts shared across storage, retrieval, diagnostics, and provider code."""

from __future__ import annotations

from enum import StrEnum


class SourceRole(StrEnum):
    USER = "user"
    OPERATOR = "operator"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    BACKGROUND = "background"
    UNKNOWN = "unknown"


class AuthorityClass(StrEnum):
    EXPLICIT_CURRENT_FACT = "explicit_current_fact"
    TYPED_CURRENT_ASSIGNMENT = "typed_current_assignment"
    CITED_SOURCE_SUPPORT = "cited_source_support"
    GRAPH_CURRENT_PRIOR_CONFLICT = "graph_current_prior_conflict"
    SUPPORTING_EVENT = "supporting_event"
    SUPPORTING_SUMMARY = "supporting_summary"
    NONE = "none"
