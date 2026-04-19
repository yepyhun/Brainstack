from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Any, Mapping, Sequence


GRAPH_EVIDENCE_BOUNDARY_VERSION = "graph_evidence_v1"
UNKNOWN_GRAPH_EVIDENCE_LANGUAGE = "und"
DEFAULT_GRAPH_EVIDENCE_PROVENANCE_CLASS = "tier1_text"

STATUS_WORDS = {"active", "paused", "archived", "completed", "retired", "pending"}
SUPERSEDE_MARKERS = (" now", " currently", " changed to", " no longer", " from ")


@dataclass(frozen=True)
class GraphEvidenceSpan:
    excerpt: str
    start_char: int | None = None
    end_char: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {"excerpt": str(self.excerpt or "").strip()}
        if self.start_char is not None:
            payload["start_char"] = int(self.start_char)
        if self.end_char is not None:
            payload["end_char"] = int(self.end_char)
        return payload


@dataclass(frozen=True)
class GraphEvidenceItem:
    kind: str
    subject: str
    predicate: str = ""
    object_value: str = ""
    attribute: str = ""
    value_text: str = ""
    confidence: float = 0.0
    language: str = UNKNOWN_GRAPH_EVIDENCE_LANGUAGE
    provenance_class: str = DEFAULT_GRAPH_EVIDENCE_PROVENANCE_CLASS
    supersede: bool = False
    evidence_span: GraphEvidenceSpan | None = None
    source_turn_id: str = ""
    source_document_id: str = ""
    temporal_scope: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "subject": self.subject,
            "confidence": float(self.confidence),
            "language": self.language,
            "provenance_class": self.provenance_class,
            "graph_evidence_boundary": GRAPH_EVIDENCE_BOUNDARY_VERSION,
        }
        if self.kind == "relation":
            payload["predicate"] = self.predicate
            payload["object_value"] = self.object_value
        else:
            payload["attribute"] = self.attribute
            payload["value_text"] = self.value_text
            payload["supersede"] = bool(self.supersede)
        if self.evidence_span is not None:
            payload["evidence_span"] = self.evidence_span.to_dict()
        if self.source_turn_id:
            payload["source_turn_id"] = self.source_turn_id
        if self.source_document_id:
            payload["source_document_id"] = self.source_document_id
        if self.temporal_scope:
            payload["temporal_scope"] = dict(self.temporal_scope)
        return payload


def _clean_value(value: str) -> str:
    return " ".join(value.strip().strip(" .").split())


def _should_supersede(sentence: str) -> bool:
    lowered = f" {sentence.lower()} "
    return any(marker in lowered for marker in SUPERSEDE_MARKERS)


def _normalize_language(language: str) -> str:
    normalized = str(language or "").strip().lower()
    return normalized or UNKNOWN_GRAPH_EVIDENCE_LANGUAGE


def _normalize_provenance_class(value: str) -> str:
    normalized = str(value or "").strip()
    return normalized or DEFAULT_GRAPH_EVIDENCE_PROVENANCE_CLASS


def _coerce_span(value: Any) -> GraphEvidenceSpan | None:
    if value is None:
        return None
    if isinstance(value, GraphEvidenceSpan):
        excerpt = str(value.excerpt or "").strip()
        if not excerpt:
            return None
        return GraphEvidenceSpan(
            excerpt=excerpt,
            start_char=value.start_char,
            end_char=value.end_char,
        )
    if not isinstance(value, Mapping):
        raise TypeError("graph evidence span must be a mapping or GraphEvidenceSpan")
    excerpt = str(value.get("excerpt") or "").strip()
    if not excerpt:
        return None
    start_char = value.get("start_char")
    end_char = value.get("end_char")
    return GraphEvidenceSpan(
        excerpt=excerpt,
        start_char=int(start_char) if start_char is not None else None,
        end_char=int(end_char) if end_char is not None else None,
    )


def coerce_graph_evidence_item(value: GraphEvidenceItem | Mapping[str, Any]) -> GraphEvidenceItem:
    if isinstance(value, GraphEvidenceItem):
        item = value
    elif isinstance(value, Mapping):
        kind = str(value.get("kind") or "").strip().lower()
        subject = _clean_value(str(value.get("subject") or ""))
        if not kind:
            raise ValueError("graph evidence item kind is required")
        if not subject:
            raise ValueError("graph evidence item subject is required")
        item = GraphEvidenceItem(
            kind=kind,
            subject=subject,
            predicate=_clean_value(str(value.get("predicate") or "")),
            object_value=_clean_value(str(value.get("object_value") or value.get("object") or "")),
            attribute=_clean_value(str(value.get("attribute") or "")),
            value_text=_clean_value(str(value.get("value_text") or value.get("value") or "")),
            confidence=float(value.get("confidence") or 0.0),
            language=_normalize_language(str(value.get("language") or "")),
            provenance_class=_normalize_provenance_class(str(value.get("provenance_class") or "")),
            supersede=bool(value.get("supersede")),
            evidence_span=_coerce_span(value.get("evidence_span")),
            source_turn_id=str(value.get("source_turn_id") or "").strip(),
            source_document_id=str(value.get("source_document_id") or "").strip(),
            temporal_scope=dict(value.get("temporal_scope") or {}) or None,
        )
    else:
        raise TypeError("graph evidence items must be mappings or GraphEvidenceItem instances")

    if item.kind not in {"relation", "state"}:
        raise ValueError(f"unsupported graph evidence kind: {item.kind}")
    if item.kind == "relation":
        if not item.predicate:
            raise ValueError("relation graph evidence requires predicate")
        if not item.object_value:
            raise ValueError("relation graph evidence requires object_value")
    if item.kind == "state":
        if not item.attribute:
            raise ValueError("state graph evidence requires attribute")
        if not item.value_text:
            raise ValueError("state graph evidence requires value_text")
    if not 0.0 <= float(item.confidence) <= 1.0:
        raise ValueError("graph evidence confidence must be between 0.0 and 1.0")
    return item


def attach_graph_source_context(
    evidence_items: Sequence[GraphEvidenceItem | Mapping[str, Any]],
    *,
    session_id: str = "",
    turn_number: int | None = None,
    source_document_id: str = "",
) -> list[GraphEvidenceItem]:
    derived_turn_id = ""
    if session_id and turn_number is not None:
        derived_turn_id = f"{session_id}:{int(turn_number)}"
    elif session_id:
        derived_turn_id = session_id
    derived_document_id = str(source_document_id or "").strip()
    bound: list[GraphEvidenceItem] = []
    for raw in evidence_items:
        item = coerce_graph_evidence_item(raw)
        if derived_turn_id and not item.source_turn_id:
            item = replace(item, source_turn_id=derived_turn_id)
        if derived_document_id and not item.source_document_id:
            item = replace(item, source_document_id=derived_document_id)
        bound.append(item)
    return bound


def extract_graph_evidence_from_text(
    text: str,
    *,
    language: str = UNKNOWN_GRAPH_EVIDENCE_LANGUAGE,
    provenance_class: str = DEFAULT_GRAPH_EVIDENCE_PROVENANCE_CLASS,
) -> list[GraphEvidenceItem]:
    evidence_items: list[GraphEvidenceItem] = []
    if not text:
        return evidence_items

    normalized_language = _normalize_language(language)
    normalized_provenance_class = _normalize_provenance_class(provenance_class)
    for sentence_match in re.finditer(r"[^.!?\n]+", text):
        sentence = str(sentence_match.group(0) or "").strip()
        if not sentence:
            continue
        cleaned = " ".join(sentence.split())
        span = GraphEvidenceSpan(
            excerpt=cleaned,
            start_char=int(sentence_match.start()),
            end_char=int(sentence_match.end()),
        )

        relation_match = re.search(
            r"(?P<subject>[A-Z][A-Za-z0-9_ /-]{1,60}?)\s+works on\s+(?P<object>[A-Z][A-Za-z0-9_ /-]{1,80})",
            cleaned,
        )
        if relation_match:
            evidence_items.append(
                GraphEvidenceItem(
                    kind="relation",
                    subject=_clean_value(relation_match.group("subject")),
                    predicate="works_on",
                    object_value=_clean_value(relation_match.group("object")),
                    confidence=0.82,
                    language=normalized_language,
                    provenance_class=normalized_provenance_class,
                    evidence_span=span,
                )
            )

        location_match = re.search(
            r"(?P<subject>[A-Z][A-Za-z0-9_ /-]{1,60}?)\s+is\s+(?:in|at)\s+(?P<value>[A-Z][A-Za-z0-9_ /-]{1,80})",
            cleaned,
        )
        if location_match:
            evidence_items.append(
                GraphEvidenceItem(
                    kind="state",
                    subject=_clean_value(location_match.group("subject")),
                    attribute="location",
                    value_text=_clean_value(location_match.group("value")),
                    supersede=_should_supersede(cleaned),
                    confidence=0.86,
                    language=normalized_language,
                    provenance_class=normalized_provenance_class,
                    evidence_span=span,
                )
            )

        status_match = re.search(
            r"(?P<subject>[A-Z][A-Za-z0-9_ /-]{1,60}?)\s+is\s+(?P<value>active|paused|archived|completed|retired|pending)(?:\s+now|\s+currently)?",
            cleaned,
            re.IGNORECASE,
        )
        if status_match:
            evidence_items.append(
                GraphEvidenceItem(
                    kind="state",
                    subject=_clean_value(status_match.group("subject")),
                    attribute="status",
                    value_text=status_match.group("value").lower(),
                    supersede=_should_supersede(cleaned),
                    confidence=0.88,
                    language=normalized_language,
                    provenance_class=normalized_provenance_class,
                    evidence_span=span,
                )
            )

    return evidence_items
