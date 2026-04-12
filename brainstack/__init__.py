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
import threading
import time
from typing import Any, Dict, List

from agent.memory_provider import MemoryProvider

from .control_plane import build_working_memory_packet
from .db import BrainstackStore
from .donors import continuity_adapter, corpus_adapter, graph_adapter
from .donors.registry import get_donor_registry
from .extraction_pipeline import build_session_message_ingest_plan, build_turn_ingest_plan
from .reconciler import reconcile_tier2_candidates
from .retrieval import (
    build_compression_hint,
    build_system_prompt_block,
)
from .tier1_extractor import build_profile_stable_key
from .tier2_extractor import extract_tier2_candidates

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
        self._transcript_match_limit = int(self._config.get("transcript_match_limit", 2))
        self._transcript_char_budget = int(self._config.get("transcript_char_budget", 560))
        self._graph_match_limit = int(self._config.get("graph_match_limit", 6))
        self._corpus_match_limit = int(self._config.get("corpus_match_limit", 4))
        self._corpus_char_budget = int(self._config.get("corpus_char_budget", 700))
        self._corpus_section_max_chars = int(self._config.get("corpus_section_max_chars", 900))
        self._tier2_idle_window_seconds = int(self._config.get("tier2_idle_window_seconds", 30))
        self._tier2_batch_turn_limit = int(self._config.get("tier2_batch_turn_limit", 5))
        self._tier2_transcript_limit = int(self._config.get("tier2_transcript_limit", 8))
        self._tier2_timeout_seconds = float(self._config.get("tier2_timeout_seconds", 15))
        self._tier2_max_tokens = int(self._config.get("tier2_max_tokens", 900))
        self._last_prefetch_policy: Dict[str, Any] | None = None
        self._last_tier2_schedule: Dict[str, Any] | None = None
        self._pending_tier2_turns = 0
        self._last_turn_monotonic: float | None = None
        self._tier2_lock = threading.RLock()
        self._tier2_thread: threading.Thread | None = None
        self._tier2_running = False
        self._tier2_followup_requested = False

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
        default_graph_db = f"{display_hermes_home()}/brainstack/brainstack.kuzu"
        default_corpus_db = f"{display_hermes_home()}/brainstack/brainstack.chroma"
        return [
            {"key": "db_path", "description": "SQLite database path", "default": default_db},
            {"key": "graph_backend", "description": "Active graph backend (kuzu recommended)", "default": "kuzu"},
            {"key": "graph_db_path", "description": "Embedded graph database path", "default": default_graph_db},
            {"key": "corpus_backend", "description": "Active corpus backend (chroma recommended)", "default": "chroma"},
            {"key": "corpus_db_path", "description": "Embedded corpus database path", "default": default_corpus_db},
            {"key": "profile_prompt_limit", "description": "How many stable profile items to keep always-on", "default": "6"},
            {"key": "profile_match_limit", "description": "How many profile matches to inject per turn", "default": "4"},
            {"key": "continuity_recent_limit", "description": "How many recent continuity items to inject", "default": "4"},
            {"key": "continuity_match_limit", "description": "How many query-matched continuity items to inject", "default": "4"},
            {"key": "transcript_match_limit", "description": "How many transcript evidence lines may be injected when strongly supported", "default": "2"},
            {"key": "transcript_char_budget", "description": "Approximate character budget for transcript evidence when it is allowed", "default": "560"},
            {"key": "graph_match_limit", "description": "How many graph-truth items to inject per turn", "default": "6"},
            {"key": "corpus_match_limit", "description": "How many corpus sections to consider per turn", "default": "4"},
            {"key": "corpus_char_budget", "description": "Approximate character budget for packed corpus recall", "default": "700"},
            {"key": "corpus_section_max_chars", "description": "Maximum size of an ingested corpus section", "default": "900"},
            {"key": "tier2_idle_window_seconds", "description": "Idle window before the future Tier-2 batch may be queued", "default": "30"},
            {"key": "tier2_batch_turn_limit", "description": "How many turns may accumulate before the future Tier-2 batch is queued", "default": "5"},
            {"key": "tier2_transcript_limit", "description": "How many recent transcript turns Tier-2 may read per batch", "default": "8"},
            {"key": "tier2_timeout_seconds", "description": "Hard timeout for one Tier-2 background extraction run", "default": "15"},
            {"key": "tier2_max_tokens", "description": "Max output tokens for one Tier-2 extraction response", "default": "900"},
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
        default_graph_db = f"{hermes_home}/brainstack/brainstack.kuzu" if hermes_home else "brainstack.kuzu"
        default_corpus_db = f"{hermes_home}/brainstack/brainstack.chroma" if hermes_home else "brainstack.chroma"
        db_path = _normalize_path(str(self._config.get("db_path", default_db)), hermes_home)
        graph_db_path = _normalize_path(str(self._config.get("graph_db_path", default_graph_db)), hermes_home)
        graph_backend = str(self._config.get("graph_backend", "kuzu") or "kuzu")
        corpus_backend = str(self._config.get("corpus_backend", "chroma") or "chroma")
        corpus_db_path = _normalize_path(str(self._config.get("corpus_db_path", default_corpus_db)), hermes_home)
        self._session_id = session_id
        self._store = BrainstackStore(
            db_path,
            graph_backend=graph_backend,
            graph_db_path=graph_db_path,
            corpus_backend=corpus_backend,
            corpus_db_path=corpus_db_path,
        )
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
            route_resolver=self._config.get("_route_resolver"),
        )
        self._last_prefetch_policy = packet["policy"]
        return packet["block"]

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        event_time: str | None = None,
    ) -> None:
        if not self._store:
            return
        sid = session_id or self._session_id
        now = time.monotonic()
        idle_seconds = None if self._last_turn_monotonic is None else max(0.0, now - self._last_turn_monotonic)
        self._last_turn_monotonic = now
        self._turn_counter += 1
        pending_turns = self._pending_tier2_turns + 1
        continuity_adapter.write_turn_records(
            self._store,
            session_id=sid,
            turn_number=self._turn_counter,
            user_content=user_content,
            assistant_content=assistant_content,
            created_at=event_time,
        )
        plan = build_turn_ingest_plan(
            user_content=user_content,
            pending_turns=pending_turns,
            idle_seconds=idle_seconds,
            idle_window_seconds=self._tier2_idle_window_seconds,
            batch_turn_limit=self._tier2_batch_turn_limit,
        )
        with self._tier2_lock:
            self._last_tier2_schedule = plan.tier2_schedule.to_dict()
            self._pending_tier2_turns = plan.tier2_schedule.pending_turns

        if not plan.durable_admission.allowed:
            logger.info(
                "Brainstack durable admission denied in sync_turn: reason=%s matched=%s",
                plan.durable_admission.reason,
                ",".join(plan.durable_admission.matched_rules) or "-",
            )

        if plan.graph_text:
            graph_adapter.ingest_turn_graph_candidates(
                self._store,
                text=plan.graph_text,
                session_id=sid,
                turn_number=self._turn_counter,
                source="sync_turn:user",
            )
        if plan.tier2_schedule.should_queue:
            self._queue_tier2_background(session_id=sid, turn_number=self._turn_counter, trigger_reason=plan.tier2_schedule.reason)

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
        worker_finished = self._wait_for_tier2_worker(timeout=self._tier2_timeout_seconds + 2.0)
        if worker_finished and (self._pending_tier2_turns > 0 or self._tier2_followup_requested):
            try:
                self._run_tier2_batch(session_id=self._session_id, turn_number=self._turn_counter, trigger_reason="session_end_flush")
            except Exception:
                logger.warning("Brainstack Tier-2 session-end flush failed", exc_info=True)
            finally:
                with self._tier2_lock:
                    self._pending_tier2_turns = 0
                    self._tier2_followup_requested = False
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
            stable_key = build_profile_stable_key(category, content)
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
        self._wait_for_tier2_worker(timeout=self._tier2_timeout_seconds + 2.0)
        if self._store:
            self._store.close()
            self._store = None
        self._last_turn_monotonic = None
        self._pending_tier2_turns = 0
        self._last_tier2_schedule = None
        self._tier2_followup_requested = False
        self._tier2_running = False
        self._tier2_thread = None

    def _queue_tier2_background(self, *, session_id: str, turn_number: int, trigger_reason: str) -> None:
        with self._tier2_lock:
            if self._tier2_running:
                self._tier2_followup_requested = True
                return
            self._tier2_running = True
            worker = threading.Thread(
                target=self._tier2_worker_loop,
                kwargs={
                    "session_id": session_id,
                    "turn_number": turn_number,
                    "trigger_reason": trigger_reason,
                },
                name="brainstack-tier2",
                daemon=True,
            )
            self._tier2_thread = worker
            worker.start()

    def _wait_for_tier2_worker(self, *, timeout: float) -> bool:
        current = threading.current_thread()
        worker: threading.Thread | None
        with self._tier2_lock:
            worker = self._tier2_thread
        if not worker or worker is current:
            return True
        worker.join(timeout=max(0.0, timeout))
        if worker.is_alive():
            logger.warning("Brainstack Tier-2 worker did not finish within %.1fs", timeout)
            return False
        return True

    def _tier2_worker_loop(self, *, session_id: str, turn_number: int, trigger_reason: str) -> None:
        current_reason = trigger_reason
        try:
            while True:
                self._run_tier2_batch(session_id=session_id, turn_number=turn_number, trigger_reason=current_reason)
                with self._tier2_lock:
                    should_continue = self._tier2_followup_requested
                    self._tier2_followup_requested = False
                    if not should_continue:
                        self._tier2_running = False
                        self._tier2_thread = None
                        break
                    current_reason = "followup_pending_work"
        except Exception:
            logger.warning("Brainstack Tier-2 worker failed", exc_info=True)
            with self._tier2_lock:
                self._tier2_running = False
                self._tier2_thread = None

    def _run_tier2_batch(self, *, session_id: str, turn_number: int, trigger_reason: str) -> None:
        if not self._store:
            return
        transcript_rows = [
            row
            for row in reversed(self._store.recent_transcript(session_id=session_id, limit=self._tier2_transcript_limit))
            if str(row.get("kind", "")) == "turn"
        ]
        if not transcript_rows:
            return
        extractor = self._config.get("_tier2_extractor")
        if callable(extractor):
            extracted = extractor(
                transcript_rows,
                session_id=session_id,
                turn_number=turn_number,
                trigger_reason=trigger_reason,
            )
        else:
            extracted = extract_tier2_candidates(
                transcript_rows,
                transcript_limit=self._tier2_transcript_limit,
                timeout_seconds=self._tier2_timeout_seconds,
                max_tokens=self._tier2_max_tokens,
            )
        reconcile_tier2_candidates(
            self._store,
            session_id=session_id,
            turn_number=turn_number,
            source=f"tier2:{trigger_reason}",
            extracted=extracted,
            metadata={
                "batch_reason": trigger_reason,
                "transcript_ids": [int(row["id"]) for row in transcript_rows if row.get("id") is not None],
            },
        )
