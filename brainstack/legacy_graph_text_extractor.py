from __future__ import annotations

import re

from .graph_evidence import (
    DEFAULT_GRAPH_EVIDENCE_PROVENANCE_CLASS,
    GraphEvidenceItem,
    GraphEvidenceSpan,
    UNKNOWN_GRAPH_EVIDENCE_LANGUAGE,
    _clean_value,
    _normalize_language,
    _normalize_provenance_class,
)

STATUS_WORDS = {"active", "paused", "archived", "completed", "retired", "pending"}
SUPERSEDE_MARKERS = (" now", " currently", " changed to", " no longer", " from ")


def _should_supersede(sentence: str) -> bool:
    lowered = f" {sentence.lower()} "
    return any(marker in lowered for marker in SUPERSEDE_MARKERS)


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

        status_pattern = r"(?P<value>" + "|".join(sorted(STATUS_WORDS)) + r")"
        status_match = re.search(
            rf"(?P<subject>[A-Z][A-Za-z0-9_ /-]{{1,60}}?)\s+is\s+{status_pattern}(?:\s+now|\s+currently)?",
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


__all__ = ["extract_graph_evidence_from_text"]
