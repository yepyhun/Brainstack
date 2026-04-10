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
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from agent.memory_provider import MemoryProvider

from .control_plane import build_working_memory_packet
from .db import BrainstackStore
from .donors import continuity_adapter, corpus_adapter, graph_adapter
from .donors.registry import get_donor_registry
from .retrieval import (
    build_compression_hint,
    build_system_prompt_block,
)

logger = logging.getLogger(__name__)


def _load_plugin_config() -> dict:
    from hermes_constants import get_hermes_home

    config_path = get_hermes_home() / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml

        with open(config_path, encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        return config.get("plugins", {}).get("brainstack", {}) or {}
    except Exception:
        return {}


def _normalize_path(value: str, hermes_home: str) -> str:
    value = value.replace("$HERMES_HOME", hermes_home)
    value = value.replace("${HERMES_HOME}", hermes_home)
    return str(Path(value).expanduser())


def _stable_key(category: str, content: str) -> str:
    normalized = " ".join(content.strip().lower().split())
    digest = hashlib.sha1(f"{category}:{normalized}".encode("utf-8")).hexdigest()
    return f"{category}:{digest[:16]}"


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"[.!?\n]+", text)
    return [part.strip() for part in parts if part and part.strip()]


def _extract_profile_candidates(text: str) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    if not text:
        return candidates

    for sentence in _split_sentences(text):
        lowered = sentence.lower()

        identity_match = re.search(
            r"\b(?:my name is|i am|i'm|call me|a nevem|én vagyok)\s+([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9_-]{2,40})",
            sentence,
            re.IGNORECASE,
        )
        if identity_match:
            value = identity_match.group(1).strip()
            content = f"User identity: {value}"
            candidates.append(
                {
                    "category": "identity",
                    "content": content,
                    "confidence": 0.95,
                    "source": "heuristic_identity",
                }
            )

        if re.search(r"\b(i prefer|i like|i love|i hate|always|never|prefer|szeretem|nem szeretem|inkább|mindig|soha)\b", lowered):
            candidates.append(
                {
                    "category": "preference",
                    "content": sentence,
                    "confidence": 0.78,
                    "source": "heuristic_preference",
                }
            )

        if re.search(r"\b(we are working on|i am working on|i'm working on|we were working on|dolgozom|dolgozunk|ezen dolgozunk)\b", lowered):
            candidates.append(
                {
                    "category": "shared_work",
                    "content": sentence,
                    "confidence": 0.7,
                    "source": "heuristic_shared_work",
                }
            )

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in candidates:
        key = _stable_key(item["category"], item["content"])
        if key in seen:
            continue
        seen.add(key)
        item["stable_key"] = key
        deduped.append(item)
    return deduped[:4]


class BrainstackMemoryProvider(MemoryProvider):
    def __init__(self, config: dict | None = None):
        self._config = config or _load_plugin_config()
        self._store: BrainstackStore | None = None
        self._session_id = ""
        self._turn_counter = 0
        self._profile_prompt_limit = int(self._config.get("profile_prompt_limit", 6))
        self._profile_match_limit = int(self._config.get("profile_match_limit", 4))
        self._continuity_recent_limit = int(self._config.get("continuity_recent_limit", 4))
        self._continuity_match_limit = int(self._config.get("continuity_match_limit", 4))
        self._compression_snapshot_limit = int(self._config.get("compression_snapshot_limit", 6))
        self._transcript_match_limit = int(self._config.get("transcript_match_limit", 1))
        self._transcript_char_budget = int(self._config.get("transcript_char_budget", 280))
        self._graph_match_limit = int(self._config.get("graph_match_limit", 6))
        self._corpus_match_limit = int(self._config.get("corpus_match_limit", 4))
        self._corpus_char_budget = int(self._config.get("corpus_char_budget", 700))
        self._corpus_section_max_chars = int(self._config.get("corpus_section_max_chars", 900))
        self._last_prefetch_policy: Dict[str, Any] | None = None

    @property
    def name(self) -> str:
        return "brainstack"

    def is_available(self) -> bool:
        return True

    def donor_registry(self) -> Dict[str, Any]:
        return {key: spec.to_dict() for key, spec in get_donor_registry().items()}

    def get_config_schema(self):
        from hermes_constants import display_hermes_home

        default_db = f"{display_hermes_home()}/brainstack/brainstack.db"
        return [
            {"key": "db_path", "description": "SQLite database path", "default": default_db},
            {"key": "profile_prompt_limit", "description": "How many stable profile items to keep always-on", "default": "6"},
            {"key": "profile_match_limit", "description": "How many profile matches to inject per turn", "default": "4"},
            {"key": "continuity_recent_limit", "description": "How many recent continuity items to inject", "default": "4"},
            {"key": "continuity_match_limit", "description": "How many query-matched continuity items to inject", "default": "4"},
            {"key": "transcript_match_limit", "description": "How many transcript evidence lines may be injected when strongly supported", "default": "1"},
            {"key": "transcript_char_budget", "description": "Approximate character budget for transcript evidence when it is allowed", "default": "280"},
            {"key": "graph_match_limit", "description": "How many graph-truth items to inject per turn", "default": "6"},
            {"key": "corpus_match_limit", "description": "How many corpus sections to consider per turn", "default": "4"},
            {"key": "corpus_char_budget", "description": "Approximate character budget for packed corpus recall", "default": "700"},
            {"key": "corpus_section_max_chars", "description": "Maximum size of an ingested corpus section", "default": "900"},
        ]

    def save_config(self, values, hermes_home):
        config_path = Path(hermes_home) / "config.yaml"
        try:
            import yaml

            existing = {}
            if config_path.exists():
                with open(config_path, encoding="utf-8") as handle:
                    existing = yaml.safe_load(handle) or {}
            existing.setdefault("plugins", {})
            existing["plugins"]["brainstack"] = values
            with open(config_path, "w", encoding="utf-8") as handle:
                yaml.safe_dump(existing, handle, default_flow_style=False, sort_keys=False)
        except Exception:
            logger.debug("Failed to save Brainstack config", exc_info=True)

    def initialize(self, session_id: str, **kwargs) -> None:
        hermes_home = str(kwargs.get("hermes_home") or "")
        default_db = f"{hermes_home}/brainstack/brainstack.db" if hermes_home else "brainstack.db"
        db_path = _normalize_path(str(self._config.get("db_path", default_db)), hermes_home)
        self._session_id = session_id
        self._store = BrainstackStore(db_path)
        self._store.open()

    def system_prompt_block(self) -> str:
        if not self._store:
            return ""
        return build_system_prompt_block(self._store, profile_limit=self._profile_prompt_limit)

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if not self._store:
            return ""
        sid = session_id or self._session_id
        packet = build_working_memory_packet(
            self._store,
            query=query,
            session_id=sid,
            profile_match_limit=self._profile_match_limit,
            continuity_recent_limit=self._continuity_recent_limit,
            continuity_match_limit=self._continuity_match_limit,
            transcript_match_limit=self._transcript_match_limit,
            transcript_char_budget=self._transcript_char_budget,
            graph_limit=self._graph_match_limit,
            corpus_limit=self._corpus_match_limit,
            corpus_char_budget=self._corpus_char_budget,
        )
        self._last_prefetch_policy = packet["policy"]
        return packet["block"]

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        if not self._store:
            return
        sid = session_id or self._session_id
        self._turn_counter += 1
        continuity_adapter.write_turn_records(
            self._store,
            session_id=sid,
            turn_number=self._turn_counter,
            user_content=user_content,
            assistant_content=assistant_content,
        )
        for item in _extract_profile_candidates(user_content):
            self._store.upsert_profile_item(
                stable_key=item["stable_key"],
                category=item["category"],
                content=item["content"],
                source=item["source"],
                confidence=float(item["confidence"]),
                metadata={"session_id": sid},
            )
        graph_adapter.ingest_turn_graph_candidates(
            self._store,
            text=user_content,
            session_id=sid,
            turn_number=self._turn_counter,
            source="sync_turn:user",
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return []

    def ingest_corpus_document(
        self,
        *,
        title: str,
        content: str,
        source: str,
        doc_kind: str = "document",
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if not self._store:
            raise RuntimeError("BrainstackStore is not initialized")
        normalized_title = " ".join(str(title).split()).strip()
        normalized_source = " ".join(str(source).split()).strip()
        text = str(content or "")
        if not normalized_title:
            raise ValueError("title is required")
        if not normalized_source:
            raise ValueError("source is required")
        if not text.strip():
            raise ValueError("content is required")

        payload = corpus_adapter.prepare_corpus_payload(
            title=normalized_title,
            content=text,
            source=normalized_source,
            doc_kind=doc_kind,
            metadata=metadata,
            section_max_chars=self._corpus_section_max_chars,
        )
        return self._store.ingest_corpus_document(
            stable_key=payload["stable_key"],
            title=normalized_title,
            doc_kind=doc_kind,
            source=normalized_source,
            sections=payload["sections"],
            metadata=metadata,
        )

    def on_turn_start(self, turn_number: int, message: str, **kwargs) -> None:
        self._turn_counter = max(self._turn_counter, turn_number - 1)

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        if not self._store:
            return ""
        summary = continuity_adapter.write_snapshot_records(
            self._store,
            session_id=self._session_id,
            turn_number=self._turn_counter,
            messages=messages,
            label="pre-compress continuity snapshot",
            kind="compression_snapshot",
            source="on_pre_compress",
            max_items=self._compression_snapshot_limit,
        )
        if not summary:
            return ""
        return build_compression_hint(summary)

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        if not self._store:
            return
        continuity_adapter.write_snapshot_records(
            self._store,
            session_id=self._session_id,
            turn_number=self._turn_counter,
            messages=messages,
            label="session summary",
            kind="session_summary",
            source="on_session_end",
            max_items=8,
        )
        for message in messages:
            if message.get("role") != "user":
                continue
            message_content = str(message.get("content", ""))
            for item in _extract_profile_candidates(str(message.get("content", ""))):
                self._store.upsert_profile_item(
                    stable_key=item["stable_key"],
                    category=item["category"],
                    content=item["content"],
                    source="session_end_scan",
                    confidence=float(item["confidence"]),
                    metadata={"session_id": self._session_id},
                )
            graph_adapter.ingest_session_graph_candidates(
                self._store,
                text=message_content,
                session_id=self._session_id,
                source="session_end_scan:user",
            )

    def on_memory_write(self, action: str, target: str, content: str) -> None:
        if not self._store or not content or action == "remove":
            return
        if target == "user":
            category = "preference"
            stable_key = _stable_key(category, content)
            self._store.upsert_profile_item(
                stable_key=stable_key,
                category=category,
                content=content,
                source=f"builtin_{action}",
                confidence=0.88,
                metadata={"target": target},
            )
            return

        self._store.add_continuity_event(
            session_id=self._session_id,
            turn_number=self._turn_counter,
            kind="builtin_memory",
            content=content,
            source=f"on_memory_write:{action}:{target}",
            metadata={"target": target},
        )

    def shutdown(self) -> None:
        if self._store:
            self._store.close()
            self._store = None
