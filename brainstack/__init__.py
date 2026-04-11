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

import logging
from pathlib import Path
import time
from typing import Any, Dict, List

from agent.memory_provider import MemoryProvider

from .control_plane import build_working_memory_packet
from .db import BrainstackStore
from .donors import continuity_adapter, corpus_adapter, graph_adapter
from .donors.registry import get_donor_registry
from .extraction_pipeline import build_session_message_ingest_plan, build_turn_ingest_plan
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
        self._tier2_idle_window_seconds = int(self._config.get("tier2_idle_window_seconds", 30))
        self._tier2_batch_turn_limit = int(self._config.get("tier2_batch_turn_limit", 5))
        self._last_prefetch_policy: Dict[str, Any] | None = None
        self._last_tier2_schedule: Dict[str, Any] | None = None
        self._pending_tier2_turns = 0
        self._last_turn_monotonic: float | None = None

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
            {"key": "tier2_idle_window_seconds", "description": "Idle window before the future Tier-2 batch may be queued", "default": "30"},
            {"key": "tier2_batch_turn_limit", "description": "How many turns may accumulate before the future Tier-2 batch is queued", "default": "5"},
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
        now = time.monotonic()
        idle_seconds = None if self._last_turn_monotonic is None else max(0.0, now - self._last_turn_monotonic)
        self._last_turn_monotonic = now
        self._turn_counter += 1
        continuity_adapter.write_turn_records(
            self._store,
            session_id=sid,
            turn_number=self._turn_counter,
            user_content=user_content,
            assistant_content=assistant_content,
        )
        plan = build_turn_ingest_plan(
            user_content=user_content,
            pending_turns=self._pending_tier2_turns + 1,
            idle_seconds=idle_seconds,
            idle_window_seconds=self._tier2_idle_window_seconds,
            batch_turn_limit=self._tier2_batch_turn_limit,
        )
        self._last_tier2_schedule = plan.tier2_schedule.to_dict()
        self._pending_tier2_turns = plan.tier2_schedule.pending_turns

        if not plan.durable_admission.allowed:
            logger.info(
                "Brainstack durable admission denied in sync_turn: reason=%s matched=%s",
                plan.durable_admission.reason,
                ",".join(plan.durable_admission.matched_rules) or "-",
            )

        for item in plan.profile_candidates:
            self._store.upsert_profile_item(
                stable_key=item["stable_key"],
                category=item["category"],
                content=item["content"],
                source=item["source"],
                confidence=float(item["confidence"]),
                metadata={
                    "session_id": sid,
                    "admission_reason": plan.durable_admission.reason,
                },
            )
        if plan.graph_text:
            graph_adapter.ingest_turn_graph_candidates(
                self._store,
                text=plan.graph_text,
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
            message_content = str(message.get("content", ""))
            plan = build_session_message_ingest_plan(
                role=str(message.get("role", "")),
                content=message_content,
            )
            if not plan.durable_admission.allowed and plan.durable_admission.reason not in {"non_user_role", "empty_fact"}:
                logger.info(
                    "Brainstack durable admission denied in session_end: reason=%s matched=%s",
                    plan.durable_admission.reason,
                    ",".join(plan.durable_admission.matched_rules) or "-",
                )
            for item in plan.profile_candidates:
                self._store.upsert_profile_item(
                    stable_key=item["stable_key"],
                    category=item["category"],
                    content=item["content"],
                    source="session_end_scan",
                    confidence=float(item["confidence"]),
                    metadata={
                        "session_id": self._session_id,
                        "admission_reason": plan.durable_admission.reason,
                    },
                )
            if plan.graph_text:
                graph_adapter.ingest_session_graph_candidates(
                    self._store,
                    text=plan.graph_text,
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
        self._last_turn_monotonic = None
        self._pending_tier2_turns = 0
        self._last_tier2_schedule = None
