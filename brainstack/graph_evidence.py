from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence


GRAPH_EVIDENCE_BOUNDARY_VERSION = "graph_evidence_v1"
UNKNOWN_GRAPH_EVIDENCE_LANGUAGE = "und"
DEFAULT_GRAPH_EVIDENCE_PROVENANCE_CLASS = "tier1_text"

@dataclass(frozen=True)
class GraphEvidenceSpan:
    excerpt: str
    start_char: int | None = None
    end_char: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"excerpt": str(self.excerpt or "").strip()}
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


class GraphEvidenceIngressError(TypeError):
    def __init__(self, receipt: Mapping[str, Any]):
        self.receipt = dict(receipt)
        summary = (
            f"graph evidence ingress rejected {int(self.receipt.get('rejected_count') or 0)} "
            f"item(s) at boundary {GRAPH_EVIDENCE_BOUNDARY_VERSION}"
        )
        super().__init__(summary)


def _clean_value(value: str) -> str:
    return " ".join(value.strip().strip(" .").split())
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
    prepared = prepare_graph_evidence_ingress(
        evidence_items,
        session_id=session_id,
        turn_number=turn_number,
        source_document_id=source_document_id,
        strict=True,
    )
    return list(prepared["items"])


def _graph_ingress_item_summary(item: GraphEvidenceItem) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "kind": item.kind,
        "subject": item.subject,
        "language": item.language,
        "provenance_class": item.provenance_class,
        "source_turn_id": item.source_turn_id,
        "source_document_id": item.source_document_id,
    }
    if item.kind == "relation":
        summary["predicate"] = item.predicate
        summary["object_value"] = item.object_value
    else:
        summary["attribute"] = item.attribute
        summary["value_text"] = item.value_text
        summary["supersede"] = bool(item.supersede)
    return summary


def prepare_graph_evidence_ingress(
    evidence_items: Sequence[GraphEvidenceItem | Mapping[str, Any]],
    *,
    session_id: str = "",
    turn_number: int | None = None,
    source_document_id: str = "",
    strict: bool = True,
) -> dict[str, Any]:
    derived_turn_id = ""
    if session_id and turn_number is not None:
        derived_turn_id = f"{session_id}:{int(turn_number)}"
    elif session_id:
        derived_turn_id = session_id
    derived_document_id = str(source_document_id or "").strip()
    accepted: list[GraphEvidenceItem] = []
    rejected: list[dict[str, Any]] = []
    for index, raw in enumerate(evidence_items):
        try:
            item = coerce_graph_evidence_item(raw)
            if derived_turn_id and not item.source_turn_id:
                item = replace(item, source_turn_id=derived_turn_id)
            if derived_document_id and not item.source_document_id:
                item = replace(item, source_document_id=derived_document_id)
            accepted.append(item)
        except (TypeError, ValueError) as exc:
            rejected.append(
                {
                    "index": index,
                    "input_type": type(raw).__name__,
                    "error": str(exc),
                }
            )

    receipt = {
        "graph_evidence_boundary": GRAPH_EVIDENCE_BOUNDARY_VERSION,
        "status": "accepted" if not rejected else ("rejected" if strict else "partial"),
        "strict": bool(strict),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "accepted_items": [_graph_ingress_item_summary(item) for item in accepted],
        "rejected_items": rejected,
        "session_id": str(session_id or "").strip(),
        "turn_number": int(turn_number) if turn_number is not None else None,
        "source_document_id": derived_document_id,
    }
    if rejected and strict:
        raise GraphEvidenceIngressError(receipt)
    return {"items": accepted, "receipt": receipt}
