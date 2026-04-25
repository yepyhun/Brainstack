from __future__ import annotations

import hashlib
import re
from typing import Any, Dict


CORPUS_TAXONOMY_SCHEMA_VERSION = "brainstack.corpus_taxonomy.v1"


def _compact(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _slug(value: Any, *, fallback: str) -> str:
    text = _compact(value).casefold()
    slug = re.sub(r"[^a-z0-9._:-]+", "-", text).strip("-")
    return slug[:80] or fallback


def _stable_hash(value: Any) -> str:
    text = _compact(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text else ""


def source_uri_is_private_path(value: Any) -> bool:
    text = _compact(value)
    if not text:
        return False
    lowered = text.casefold()
    return (
        text.startswith("/")
        or text.startswith("~/")
        or lowered.startswith("file:")
        or bool(re.match(r"^[a-z]:[\\/]", text, flags=re.IGNORECASE))
    )


def public_source_uri(value: Any, *, source_adapter: str, source_id: str) -> str:
    text = _compact(value)
    if not text:
        return _slug(source_id or source_adapter, fallback="source")
    if source_uri_is_private_path(text):
        digest = _stable_hash(text)
        prefix = _slug(source_adapter, fallback="local")
        return f"{prefix}:private:{digest}"
    return text


def build_corpus_taxonomy_metadata(
    *,
    source_adapter: str,
    source_id: str,
    stable_key: str,
    title: str,
    doc_kind: str,
    source_uri: str,
) -> Dict[str, Any]:
    public_uri = public_source_uri(source_uri, source_adapter=source_adapter, source_id=source_id)
    wing = _slug(doc_kind, fallback="document")
    room = _slug(source_adapter, fallback="manual")
    drawer = _slug(stable_key or title or source_id, fallback="document")
    taxonomy: Dict[str, Any] = {
        "schema": CORPUS_TAXONOMY_SCHEMA_VERSION,
        "donor": "MemPalace",
        "mapping": "adapted_wing_room_drawer",
        "wing": wing,
        "room": room,
        "drawer": drawer,
        "display_source_id": f"{wing}/{room}/{drawer}",
        "public_source_uri": public_uri,
    }
    if source_uri_is_private_path(source_uri):
        taxonomy["private_source_uri_hash"] = _stable_hash(source_uri)
        taxonomy["source_uri_redacted"] = True
    else:
        taxonomy["source_uri_redacted"] = False
    return taxonomy
