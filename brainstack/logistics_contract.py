from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


def derive_transcript_logistics_typed_entities(
    transcript_entries: Iterable[Mapping[str, Any]],
    *,
    existing_entities: Iterable[Mapping[str, Any]],
    source: str = "tier2_transcript_rule",
) -> List[Dict[str, Any]]:
    del transcript_entries, existing_entities, source
    return []
