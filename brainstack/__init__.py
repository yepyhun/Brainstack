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
import json
import logging
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, List

from agent.memory_provider import MemoryProvider

from .control_plane import build_working_memory_packet
from .db import BrainstackStore
from .donors import continuity_adapter, corpus_adapter, graph_adapter
from .donors.registry import get_donor_registry
from .extraction_pipeline import build_session_message_ingest_plan, build_turn_ingest_plan
from .operating_truth import (
    OPERATING_OWNER,
    build_operating_stable_key,
    parse_operating_capture,
)
from .output_contract import validate_output_against_contract
from .reconciler import reconcile_tier2_candidates
from .retrieval import (
    build_compression_hint,
    build_system_prompt_projection,
)
from .style_contract import (
    apply_style_contract_patch,
    build_style_contract_from_text,
    list_style_contract_rules,
    looks_like_style_contract_teaching,
)
from .task_memory import build_task_stable_key, parse_task_capture, resolve_user_timezone
from .tier1_extractor import build_profile_stable_key
from .tier2_extractor import extract_tier2_candidates

logger = logging.getLogger(__name__)


def _build_personal_scope_key(*, platform: str = "", user_id: str = "") -> str:
    parts: List[str] = []
    normalized_platform = str(platform or "").strip()
    normalized_user_id = str(user_id or "").strip()
    if normalized_platform:
        parts.append(f"platform:{normalized_platform}")
    if normalized_user_id:
        parts.append(f"user_id:{normalized_user_id}")
    return "|".join(parts)


def _load_plugin_config() -> dict:
    from hermes_constants import get_hermes_home

    config_path = get_hermes_home() / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml  # type: ignore[import-untyped]

        with open(config_path, encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        return config.get("plugins", {}).get("brainstack", {}) or {}
    except Exception:
        return {}


def _normalize_path(value: str, hermes_home: str) -> str:
    value = value.replace("$HERMES_HOME", hermes_home)
    value = value.replace("${HERMES_HOME}", hermes_home)
    return str(Path(value).expanduser())


def _debug_row_snapshot(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "session_id": str(row.get("session_id") or ""),
        "turn_number": int(row.get("turn_number") or 0),
        "stable_key": str(row.get("stable_key") or ""),
        "row_type": str(row.get("row_type") or ""),
        "document_id": int(row.get("document_id") or 0),
        "section_index": int(row.get("section_index") or 0),
        "created_at": str(row.get("created_at") or ""),
        "keyword_score": float(row.get("keyword_score") or 0.0),
        "semantic_score": float(row.get("semantic_score") or 0.0),
        "channels": list(row.get("_brainstack_channels") or []),
        "channel_ranks": dict(row.get("_brainstack_channel_ranks") or {}),
        "rrf_score": float(row.get("_brainstack_rrf_score") or 0.0),
        "content_excerpt": str(row.get("content") or "")[:240],
    }


def _build_principal_scope(**kwargs: Any) -> Dict[str, str]:
    user_id = str(kwargs.get("user_id") or "").strip()
    if not user_id:
        return {}
    platform = str(kwargs.get("platform") or "").strip()
    agent_identity = str(kwargs.get("agent_identity") or "").strip()
    agent_workspace = str(kwargs.get("agent_workspace") or "").strip()
    timezone_name = resolve_user_timezone(kwargs.get("timezone"))
    scope: Dict[str, str] = {"user_id": user_id}
    if platform:
        scope["platform"] = platform
    if agent_identity:
        scope["agent_identity"] = agent_identity
    if agent_workspace:
        scope["agent_workspace"] = agent_workspace
    if timezone_name and timezone_name != "UTC":
        scope["timezone"] = timezone_name
    personal_scope_key = _build_personal_scope_key(platform=platform, user_id=user_id)
    if personal_scope_key:
        scope["personal_scope_key"] = personal_scope_key
    key_parts: List[str] = []
    for key in ("platform", "user_id", "agent_identity", "agent_workspace"):
        value = str(scope.get(key) or "").strip()
        if value:
            key_parts.append(f"{key}:{value}")
    if key_parts:
        scope["principal_scope_key"] = "|".join(key_parts)
    return scope


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
        self._operating_match_limit = int(self._config.get("operating_match_limit", 3))
        self._graph_match_limit = int(self._config.get("graph_match_limit", 6))
        self._corpus_match_limit = int(self._config.get("corpus_match_limit", 4))
        self._corpus_char_budget = int(self._config.get("corpus_char_budget", 700))
        self._corpus_section_max_chars = int(self._config.get("corpus_section_max_chars", 900))
        self._tier2_idle_window_seconds = int(self._config.get("tier2_idle_window_seconds", 30))
        self._tier2_batch_turn_limit = int(self._config.get("tier2_batch_turn_limit", 5))
        self._tier2_transcript_limit = int(self._config.get("tier2_transcript_limit", 8))
        self._tier2_timeout_seconds = float(self._config.get("tier2_timeout_seconds", 15))
        self._tier2_max_tokens = int(self._config.get("tier2_max_tokens", 900))
        self._route_resolver_override = None
        self._last_prefetch_policy: Dict[str, Any] | None = None
        self._last_prefetch_routing: Dict[str, Any] | None = None
        self._last_prefetch_channels: list[Dict[str, Any]] | None = None
        self._last_prefetch_debug: Dict[str, Any] | None = None
        self._last_behavior_policy_trace: Dict[str, Any] | None = None
        self._last_operating_context_trace: Dict[str, Any] | None = None
        self._last_memory_operation_trace: Dict[str, Any] | None = None
        self._last_write_receipt: Dict[str, Any] | None = None
        self._last_tier2_schedule: Dict[str, Any] | None = None
        self._last_tier2_batch_result: Dict[str, Any] | None = None
        self._tier2_batch_history: List[Dict[str, Any]] = []
        self._pending_tier2_turns = 0
        self._pending_explicit_write_count = 0
        self._write_receipt_counter = 0
        self._last_turn_monotonic: float | None = None
        self._user_timezone = resolve_user_timezone(self._config.get("user_timezone"))
        self._tier2_lock = threading.RLock()
        self._tier2_thread: threading.Thread | None = None
        self._tier2_running = False
        self._tier2_followup_requested = False
        self._principal_scope: Dict[str, str] = {}
        self._principal_scope_key = ""
        self._recent_user_messages: List[str] = []

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
            {"key": "operating_match_limit", "description": "How many operating-truth items to consider per turn", "default": "3"},
            {"key": "graph_match_limit", "description": "How many graph-truth items to inject per turn", "default": "6"},
            {"key": "corpus_match_limit", "description": "How many corpus sections to consider per turn", "default": "4"},
            {"key": "corpus_char_budget", "description": "Approximate character budget for packed corpus recall", "default": "700"},
            {"key": "corpus_section_max_chars", "description": "Maximum size of an ingested corpus section", "default": "900"},
            {"key": "user_timezone", "description": "Default timezone for relative task and commitment dates", "default": "UTC"},
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

    def _reset_session_runtime_state(self) -> None:
        self._session_id = ""
        self._turn_counter = 0
        self._last_prefetch_policy = None
        self._last_prefetch_routing = None
        self._last_prefetch_channels = []
        self._last_prefetch_debug = None
        self._last_behavior_policy_trace = None
        self._last_operating_context_trace = None
        self._last_memory_operation_trace = None
        self._last_write_receipt = None
        self._last_tier2_schedule = None
        self._last_tier2_batch_result = None
        self._tier2_batch_history = []
        self._pending_tier2_turns = 0
        self._pending_explicit_write_count = 0
        self._write_receipt_counter = 0
        self._last_turn_monotonic = None
        self._tier2_followup_requested = False
        self._tier2_running = False
        self._tier2_thread = None
        self._principal_scope = {}
        self._principal_scope_key = ""
        self._recent_user_messages = []

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
        worker_finished = self._wait_for_tier2_worker(timeout=self._tier2_timeout_seconds + 2.0)
        if not worker_finished:
            raise RuntimeError("Cannot reinitialize Brainstack while the Tier-2 worker is still running.")
        if self._store:
            self._store.close()
            self._store = None
        self._reset_session_runtime_state()
        self._session_id = session_id
        self._principal_scope = _build_principal_scope(**kwargs)
        self._principal_scope_key = str(self._principal_scope.get("principal_scope_key") or "").strip()
        self._user_timezone = resolve_user_timezone(
            kwargs.get("timezone")
            or self._principal_scope.get("timezone")
            or self._config.get("user_timezone")
        )
        self._store = BrainstackStore(
            db_path,
            graph_backend=graph_backend,
            graph_db_path=graph_db_path,
            corpus_backend=corpus_backend,
            corpus_db_path=corpus_db_path,
        )
        self._store.open()

    def _scoped_metadata(self, metadata: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
        payload = dict(metadata or {})
        if self._user_timezone:
            payload.setdefault("timezone", self._user_timezone)
        if self._principal_scope_key:
            payload.setdefault("principal_scope_key", self._principal_scope_key)
            payload.setdefault("principal_scope", dict(self._principal_scope))
        return payload or None

    def _next_write_receipt_id(self) -> str:
        self._write_receipt_counter += 1
        session_label = self._session_id or "session"
        return f"{session_label}:write:{self._write_receipt_counter}"

    def _memory_operation_state(
        self,
        *,
        surface: str = "",
        note: str = "",
    ) -> Dict[str, Any]:
        state = {
            "pending_explicit_write_count": int(self._pending_explicit_write_count),
            "barrier_clear": self._pending_explicit_write_count == 0,
            "last_write_receipt": dict(self._last_write_receipt or {}),
        }
        if surface:
            state["surface"] = surface
        if note:
            state["note"] = note
        return state

    def _set_memory_operation_trace(
        self,
        *,
        surface: str,
        note: str = "",
    ) -> Dict[str, Any]:
        trace = self._memory_operation_state(surface=surface, note=note)
        self._last_memory_operation_trace = trace
        return trace

    def _commit_explicit_write(
        self,
        *,
        owner: str,
        write_class: str,
        source: str,
        target: str,
        stable_key: str,
        category: str,
        content: str,
        commit: Callable[[], None],
        extra: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        receipt = {
            "receipt_id": self._next_write_receipt_id(),
            "status": "pending",
            "owner": owner,
            "write_class": write_class,
            "target": target,
            "stable_key": stable_key,
            "category": category,
            "source": source,
            "session_id": self._session_id,
            "turn_number": int(self._turn_counter),
            "principal_scope_key": self._principal_scope_key,
            "content_hash": hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()
            if str(content or "")
            else "",
        }
        if isinstance(extra, dict):
            receipt.update(extra)

        self._pending_explicit_write_count += 1
        self._last_write_receipt = dict(receipt)
        self._set_memory_operation_trace(surface="explicit_write_pending")
        try:
            commit()
        except Exception as exc:
            failed = dict(receipt)
            failed["status"] = "failed"
            failed["error"] = str(exc)
            self._last_write_receipt = failed
            raise
        finally:
            self._pending_explicit_write_count = max(0, self._pending_explicit_write_count - 1)

        committed = dict(receipt)
        committed["status"] = "committed"
        self._last_write_receipt = committed
        self._set_memory_operation_trace(surface="explicit_write_committed")
        return committed

    def _ensure_explicit_write_barrier_clear(self, *, surface: str) -> bool:
        clear = self._pending_explicit_write_count == 0
        note = "" if clear else "Explicit durable write is still pending; refusing teardown."
        self._set_memory_operation_trace(surface=surface, note=note)
        if not clear:
            logger.error(note)
        return clear

    def _render_memory_operation_receipt_block(self, receipt: Dict[str, Any] | None) -> str:
        if not isinstance(receipt, dict):
            return ""
        if str(receipt.get("status") or "").strip() != "committed":
            return ""
        lines = [
            f"Committed durable write for this session: {receipt.get('write_class', 'write')}.",
            f"Owner: {receipt.get('owner', 'brainstack')}.",
            "This is committed evidence, not a plan or an optimistic promise.",
        ]
        source = str(receipt.get("source") or "").strip()
        if source:
            lines.append(f"Write source: {source}.")
        item_count = int(receipt.get("item_count") or 0)
        if item_count > 0:
            lines.append(f"Committed items: {item_count}.")
        due_date = str(receipt.get("due_date") or "").strip()
        if due_date:
            lines.append(f"Due date: {due_date}.")
        return "## Brainstack Memory Operation Receipt\n" + "\n".join(f"- {line}" for line in lines)

    def _upsert_style_contract_candidate(
        self,
        *,
        content: str,
        source: str,
        confidence: float = 0.9,
        metadata: Dict[str, Any] | None = None,
        require_explicit_signal: bool = False,
    ) -> Dict[str, Any] | None:
        if not self._store or not content:
            return None
        style_contract = self._resolve_style_contract_candidate(
            content=content,
            source=source,
            confidence=confidence,
            metadata=metadata,
            require_explicit_signal=require_explicit_signal,
        )
        self._remember_recent_user_message(content)
        if style_contract is None:
            return None

        receipt = self._commit_explicit_write(
            owner="brainstack.behavior_contract",
            write_class="style_contract",
            source=str(style_contract["source"]),
            target="user",
            stable_key=str(style_contract["slot"]),
            category=str(style_contract["category"]),
            content=str(style_contract["content"]),
            commit=lambda: self._store.upsert_behavior_contract(
                stable_key=style_contract["slot"],
                category=style_contract["category"],
                content=style_contract["content"],
                source=style_contract["source"],
                confidence=float(style_contract["confidence"]),
                metadata=style_contract["metadata"],
            ),
            extra={
                "rule_count": int(style_contract.get("metadata", {}).get("style_contract_rule_count") or 0),
                "fragment_count": int(style_contract.get("metadata", {}).get("style_contract_fragment_count") or 1),
                "patch_rule_count": int(
                    style_contract.get("metadata", {}).get("last_style_contract_patch", {}).get("patch_rule_count") or 0
                ),
            },
        )
        raw_contract = self._store.get_behavior_contract(principal_scope_key=self._principal_scope_key)
        snapshot = self._store.get_behavior_policy_snapshot(principal_scope_key=self._principal_scope_key)
        compiled_policy = dict(snapshot.get("compiled_policy") or {})
        receipt["behavior_contract_revision"] = int(raw_contract.get("revision_number") or 0) if raw_contract else 0
        receipt["behavior_contract_storage_key"] = str(raw_contract.get("storage_key") or "") if raw_contract else ""
        receipt["compiled_policy_active"] = bool(compiled_policy.get("active"))
        receipt["compiled_policy_status"] = str(compiled_policy.get("status") or "")
        self._last_write_receipt = receipt
        self._set_memory_operation_trace(surface="style_contract_upsert")
        return receipt

    def _remember_recent_user_message(self, content: str) -> None:
        text = str(content or "").strip()
        if not text:
            return
        if self._recent_user_messages and self._recent_user_messages[-1] == text:
            return
        self._recent_user_messages.append(text)
        if len(self._recent_user_messages) > 4:
            self._recent_user_messages = self._recent_user_messages[-4:]

    def _iter_style_contract_candidate_texts(self, content: str) -> List[tuple[str, int]]:
        text = str(content or "").strip()
        if not text:
            return []
        prior_fragments = [
            fragment
            for fragment in self._recent_user_messages
            if str(fragment or "").strip() and str(fragment or "").strip() != text
        ]
        candidates: List[tuple[str, int]] = []
        seen: set[str] = set()

        def _add(raw_text: str, fragment_count: int) -> None:
            normalized = str(raw_text or "").strip()
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            candidates.append((normalized, fragment_count))

        _add(text, 1)
        if "\n" not in text:
            return candidates
        for fragment_count in range(1, min(len(prior_fragments), 2) + 1):
            _add("\n".join([*prior_fragments[-fragment_count:], text]), fragment_count + 1)
        return candidates

    def _resolve_style_contract_candidate(
        self,
        *,
        content: str,
        source: str,
        confidence: float,
        metadata: Dict[str, Any] | None,
        require_explicit_signal: bool,
    ) -> Dict[str, Any] | None:
        scoped_metadata = self._scoped_metadata(metadata)
        best_candidate: Dict[str, Any] | None = None
        best_score: tuple[int, int, int] | None = None
        for raw_text, fragment_count in self._iter_style_contract_candidate_texts(content):
            if require_explicit_signal and not looks_like_style_contract_teaching(raw_text):
                continue
            candidate = build_style_contract_from_text(
                raw_text=raw_text,
                source=source,
                confidence=confidence,
                metadata={
                    **scoped_metadata,
                    "style_contract_fragment_count": fragment_count,
                },
            )
            if candidate is None:
                continue
            rule_count = int(
                candidate.get("metadata", {}).get("style_contract_rule_count")
                or len(list_style_contract_rules(raw_text=raw_text, metadata=candidate.get("metadata")))
            )
            score = (rule_count, len(str(candidate.get("content") or "")), fragment_count)
            if best_score is None or score > best_score:
                best_candidate = candidate
                best_score = score
        if best_candidate is not None:
            return best_candidate

        if not self._store:
            return None
        raw_contract = self._store.get_behavior_contract(principal_scope_key=self._principal_scope_key)
        if raw_contract is None:
            return None

        patch_source = source.replace(":style_contract", ":style_contract_patch")
        scoped_metadata = self._scoped_metadata(metadata)
        for raw_text, fragment_count in self._iter_style_contract_candidate_texts(content):
            corrected = apply_style_contract_patch(
                raw_text=raw_contract.get("content"),
                patch_text=raw_text,
                metadata=raw_contract.get("metadata"),
            )
            if corrected is None:
                continue
            merged_metadata = {
                **dict(raw_contract.get("metadata") or {}),
                **scoped_metadata,
                "memory_class": "style_contract",
                "style_contract_title": corrected["title"],
                "style_contract_sections": corrected["sections"],
                "style_contract_rule_count": len(
                    list_style_contract_rules(raw_text=corrected["content"], metadata={"style_contract_sections": corrected["sections"]})
                ),
                "style_contract_fragment_count": fragment_count,
                "last_style_contract_patch": {
                    "updated_rule_ids": list(corrected.get("updated_rule_ids") or []),
                    "patch_rule_count": int(corrected.get("patch_rule_count") or 0),
                    "source": patch_source,
                },
            }
            return {
                "category": str(raw_contract.get("category") or "preference"),
                "slot": str(raw_contract.get("stable_key") or "preference:style_contract"),
                "content": str(corrected["content"]),
                "confidence": float(raw_contract.get("confidence") or confidence or 0.9),
                "source": patch_source,
                "metadata": merged_metadata,
            }
        return None

    def _upsert_task_capture_candidate(
        self,
        *,
        content: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        if not self._store or not content:
            return None
        capture = parse_task_capture(content, timezone_name=self._user_timezone)
        if capture is None:
            return None

        items = list(capture.get("items") or [])
        if not items:
            return None
        item_type = str(capture.get("item_type") or "task").strip() or "task"
        due_date = str(capture.get("due_date") or "").strip()
        date_scope = str(capture.get("date_scope") or "").strip()
        batch_stable_key = build_task_stable_key(
            principal_scope_key=self._principal_scope_key,
            item_type=item_type,
            due_date=due_date,
            title=" | ".join(str(item.get("title") or "").strip() for item in items),
        )

        def commit() -> None:
            scoped_metadata = self._scoped_metadata(metadata)
            for item in items:
                title = str(item.get("title") or "").strip()
                item_due_date = str(item.get("due_date") or due_date).strip()
                item_date_scope = str(item.get("date_scope") or date_scope).strip()
                stable_key = build_task_stable_key(
                    principal_scope_key=self._principal_scope_key,
                    item_type=str(item.get("item_type") or item_type).strip() or item_type,
                    due_date=item_due_date,
                    title=title,
                )
                self._store.upsert_task_item(
                    stable_key=stable_key,
                    principal_scope_key=self._principal_scope_key,
                    item_type=str(item.get("item_type") or item_type).strip() or item_type,
                    title=title,
                    due_date=item_due_date,
                    date_scope=item_date_scope,
                    optional=bool(item.get("optional")),
                    status=str(item.get("status") or "open").strip() or "open",
                    owner="brainstack.task_memory",
                    source=source,
                    source_session_id=str((metadata or {}).get("session_id") or self._session_id or "").strip(),
                    source_turn_number=int((metadata or {}).get("turn_number") or self._turn_counter or 0),
                    metadata=scoped_metadata,
                )

        receipt = self._commit_explicit_write(
            owner="brainstack.task_memory",
            write_class="task_memory",
            source=source,
            target="user",
            stable_key=batch_stable_key,
            category=item_type,
            content=content,
            commit=commit,
            extra={
                "item_count": len(items),
                "due_date": due_date,
                "date_scope": date_scope,
                "items": [
                    {
                        "title": str(item.get("title") or "").strip(),
                        "optional": bool(item.get("optional")),
                        "due_date": str(item.get("due_date") or due_date).strip(),
                    }
                    for item in items
                ],
            },
        )
        self._last_write_receipt = receipt
        self._set_memory_operation_trace(surface="task_capture_upsert")
        return receipt

    def _upsert_operating_truth_candidate(
        self,
        *,
        content: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        if not self._store or not content:
            return None
        capture = parse_operating_capture(content)
        if capture is None:
            return None

        items = list(capture.get("items") or [])
        if not items:
            return None

        batch_stable_key = "::".join(
            [
                "operating_truth_batch",
                self._principal_scope_key or "global",
                str((metadata or {}).get("session_id") or self._session_id or "").strip() or "session",
                str((metadata or {}).get("turn_number") or self._turn_counter or 0),
            ]
        )

        def commit() -> None:
            scoped_metadata = self._scoped_metadata(metadata)
            for item in items:
                record_type = str(item.get("record_type") or "").strip()
                content_text = str(item.get("content") or "").strip()
                if not record_type or not content_text:
                    continue
                stable_key = build_operating_stable_key(
                    principal_scope_key=self._principal_scope_key,
                    record_type=record_type,
                    content=content_text,
                )
                self._store.upsert_operating_record(
                    stable_key=stable_key,
                    principal_scope_key=self._principal_scope_key,
                    record_type=record_type,
                    content=content_text,
                    owner=OPERATING_OWNER,
                    source=source,
                    source_session_id=str((metadata or {}).get("session_id") or self._session_id or "").strip(),
                    source_turn_number=int((metadata or {}).get("turn_number") or self._turn_counter or 0),
                    metadata=scoped_metadata,
                )

        receipt = self._commit_explicit_write(
            owner=OPERATING_OWNER,
            write_class="operating_truth",
            source=source,
            target="user",
            stable_key=batch_stable_key,
            category="operating_truth",
            content=content,
            commit=commit,
            extra={
                "item_count": len(items),
                "record_types": [str(item.get("record_type") or "").strip() for item in items],
                "items": [dict(item) for item in items],
            },
        )
        self._last_write_receipt = receipt
        self._set_memory_operation_trace(surface="operating_truth_upsert")
        return receipt

    def system_prompt_block(self) -> str:
        if not self._store:
            return ""
        projection = build_system_prompt_projection(
            self._store,
            profile_limit=self._profile_prompt_limit,
            principal_scope_key=self._principal_scope_key,
            session_id=self._session_id,
        )
        block = str(projection.get("block") or "")
        snapshot = self._store.get_behavior_policy_snapshot(principal_scope_key=self._principal_scope_key)
        trace = dict(self._last_behavior_policy_trace or {})
        contract_title = str(snapshot.get("compiled_policy", {}).get("title") or "")
        trace["system_prompt_block"] = {
            "surface": "system_prompt_block",
            "injected": bool(contract_title and contract_title in block),
            "section_present": "# Brainstack Active Communication Contract" in block,
            "title_present": bool(contract_title and contract_title in block),
            "snapshot": snapshot,
            "projection": dict(projection),
        }
        self._last_behavior_policy_trace = trace
        operating_snapshot = self._store.get_operating_context_snapshot(
            principal_scope_key=self._principal_scope_key,
            session_id=self._session_id,
        )
        operating_trace = dict(self._last_operating_context_trace or {})
        operating_trace["system_prompt_block"] = {
            "surface": "system_prompt_block",
            "section_present": "# Brainstack Operating Context" in block,
            "active_work_present": bool(str(operating_snapshot.get("active_work_summary") or "").strip()),
            "open_decisions_present": bool(list(operating_snapshot.get("open_decisions") or [])),
            "snapshot": operating_snapshot,
        }
        self._last_operating_context_trace = operating_trace
        return block

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if not self._store:
            return ""
        sid = session_id or self._session_id
        style_contract_receipt = self._upsert_style_contract_candidate(
            content=query,
            source="prefetch:style_contract",
            confidence=0.9,
            metadata={"session_id": sid},
            require_explicit_signal=True,
        )
        style_contract_activated = style_contract_receipt is not None
        task_capture_receipt = self._upsert_task_capture_candidate(
            content=query,
            source="prefetch:task_memory",
            metadata={"session_id": sid},
        )
        operating_truth_receipt = self._upsert_operating_truth_candidate(
            content=query,
            source="prefetch:operating_truth",
            metadata={"session_id": sid},
        )
        system_substrate = build_system_prompt_projection(
            self._store,
            profile_limit=self._profile_prompt_limit,
            principal_scope_key=self._principal_scope_key,
            session_id=sid,
        )
        packet = build_working_memory_packet(
            self._store,
            query=query,
            session_id=sid,
            principal_scope_key=self._principal_scope_key,
            timezone_name=self._user_timezone,
            profile_match_limit=self._profile_match_limit,
            continuity_recent_limit=self._continuity_recent_limit,
            continuity_match_limit=self._continuity_match_limit,
            transcript_match_limit=self._transcript_match_limit,
            transcript_char_budget=self._transcript_char_budget,
            operating_match_limit=self._operating_match_limit,
            graph_limit=self._graph_match_limit,
            corpus_limit=self._corpus_match_limit,
            corpus_char_budget=self._corpus_char_budget,
            route_resolver=self._route_resolver_override or self._config.get("_route_resolver"),
            system_substrate=system_substrate,
        )
        self._last_prefetch_policy = packet["policy"]
        self._last_prefetch_routing = dict(packet.get("routing") or {})
        self._last_prefetch_channels = [
            dict(channel)
            for channel in list(packet.get("channels") or [])
            if isinstance(channel, dict)
        ]
        if bool(getattr(self, "_capture_candidate_debug", False)) or bool(self._config.get("_capture_candidate_debug")):
            self._last_prefetch_debug = {
                "fused_candidates": [dict(item) for item in list(packet.get("fused_candidates") or [])],
                "selected_rows": {
                    "profile_items": [_debug_row_snapshot(row) for row in list(packet.get("profile_items") or [])],
                    "matched": [_debug_row_snapshot(row) for row in list(packet.get("matched") or [])],
                    "recent": [_debug_row_snapshot(row) for row in list(packet.get("recent") or [])],
                    "transcript_rows": [_debug_row_snapshot(row) for row in list(packet.get("transcript_rows") or [])],
                    "operating_rows": [dict(row) for row in list(packet.get("operating_rows") or [])],
                    "graph_rows": [_debug_row_snapshot(row) for row in list(packet.get("graph_rows") or [])],
                    "corpus_rows": [_debug_row_snapshot(row) for row in list(packet.get("corpus_rows") or [])],
                    "task_rows": [dict(row) for row in list(packet.get("task_rows") or [])],
                },
            }
        else:
            self._last_prefetch_debug = None
        snapshot = self._store.get_behavior_policy_snapshot(principal_scope_key=self._principal_scope_key)
        trace = dict(self._last_behavior_policy_trace or {})
        compiled_policy = packet.get("policy", {}).get("compiled_behavior_policy")
        projection_text = ""
        if isinstance(compiled_policy, dict):
            projection_text = str(compiled_policy.get("projection_text") or "").strip()
        reinforcement = packet.get("policy", {}).get("behavior_policy_reinforcement")
        output_block = str(packet.get("block") or "")
        receipt_blocks = [
            self._render_memory_operation_receipt_block(receipt)
            for receipt in (style_contract_receipt, task_capture_receipt, operating_truth_receipt)
            if isinstance(receipt, dict)
        ]
        if receipt_blocks:
            output_block = "\n\n".join(
                part for part in (output_block, *receipt_blocks) if str(part).strip()
            )
        trace["prefetch"] = {
            "surface": "prefetch",
            "route_mode": str(packet.get("routing", {}).get("applied_mode") or "fact"),
            "style_contract_activated_before_prefetch": style_contract_activated,
            "task_capture_activated_before_prefetch": bool(task_capture_receipt),
            "operating_truth_activated_before_prefetch": bool(operating_truth_receipt),
            "write_receipt_present": bool(style_contract_receipt or task_capture_receipt or operating_truth_receipt),
            "write_receipt_status": str(
                (operating_truth_receipt or task_capture_receipt or style_contract_receipt or {}).get("status") or ""
            ),
            "compiled_policy_present_in_packet": bool(isinstance(compiled_policy, dict) and projection_text),
            "projection_present_in_block": bool(projection_text and projection_text in output_block),
            "correction_reinforcement_present": bool(
                isinstance(reinforcement, dict) and str(reinforcement.get("text") or "").strip()
            ),
            "correction_reinforcement_mode": str(reinforcement.get("mode") or "")
            if isinstance(reinforcement, dict)
            else "",
            "snapshot": snapshot,
        }
        self._last_behavior_policy_trace = trace
        return output_block

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
            metadata=self._scoped_metadata(),
        )
        self._upsert_style_contract_candidate(
            content=user_content,
            source="sync_turn:user_style_contract",
            confidence=0.9,
            metadata={"session_id": sid, "turn_number": self._turn_counter},
            require_explicit_signal=True,
        )
        self._upsert_operating_truth_candidate(
            content=user_content,
            source="sync_turn:operating_truth",
            metadata={"session_id": sid, "turn_number": self._turn_counter},
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

        if plan.graph_evidence_items:
            graph_adapter.ingest_turn_graph_candidates(
                self._store,
                evidence_items=plan.graph_evidence_items,
                session_id=sid,
                turn_number=self._turn_counter,
                source="sync_turn:user",
                metadata=self._scoped_metadata(),
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
        snapshot_window = continuity_adapter.build_snapshot_source_window(
            messages,
            max_items=self._compression_snapshot_limit,
        )
        summary = continuity_adapter.write_snapshot_records(
            self._store,
            session_id=self._session_id,
            turn_number=self._turn_counter,
            messages=messages,
            label="pre-compress continuity snapshot",
            kind="compression_snapshot",
            source="on_pre_compress",
            max_items=self._compression_snapshot_limit,
            metadata=self._scoped_metadata(),
        )
        if not summary:
            return ""
        self._store.record_continuity_snapshot_state(
            session_id=self._session_id,
            turn_number=self._turn_counter,
            kind="compression_snapshot",
            message_count=int(snapshot_window.get("captured_message_count") or 0),
            input_message_count=int(snapshot_window.get("input_message_count") or 0),
            digest=str(snapshot_window.get("window_digest") or ""),
        )
        return build_compression_hint(summary)

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        if not self._store:
            return
        if not self._ensure_explicit_write_barrier_clear(surface="on_session_end"):
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
        snapshot_window = continuity_adapter.build_snapshot_source_window(messages, max_items=8)
        summary = continuity_adapter.write_snapshot_records(
            self._store,
            session_id=self._session_id,
            turn_number=self._turn_counter,
            messages=messages,
            label="session summary",
            kind="session_summary",
            source="on_session_end",
            max_items=8,
            metadata=self._scoped_metadata(),
        )
        if summary:
            self._store.record_continuity_snapshot_state(
                session_id=self._session_id,
                turn_number=self._turn_counter,
                kind="session_summary",
                message_count=int(snapshot_window.get("captured_message_count") or 0),
                input_message_count=int(snapshot_window.get("input_message_count") or 0),
                digest=str(snapshot_window.get("window_digest") or ""),
            )
        self._store.finalize_continuity_session_state(
            session_id=self._session_id,
            turn_number=self._turn_counter,
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
            if plan.graph_evidence_items:
                graph_adapter.ingest_session_graph_candidates(
                    self._store,
                    evidence_items=plan.graph_evidence_items,
                    session_id=self._session_id,
                    source="session_end_scan:user",
                    metadata=self._scoped_metadata(),
                )

    def on_memory_write(self, action: str, target: str, content: str) -> None:
        if not self._store or not content or action == "remove":
            return
        if target == "user":
            if self._upsert_style_contract_candidate(
                content=content,
                source=f"builtin_{action}:style_contract",
                confidence=0.9,
                metadata={"target": target},
            ):
                return
            if self._upsert_task_capture_candidate(
                content=content,
                source=f"builtin_{action}:task_memory",
                metadata={"target": target},
            ):
                return
            scoped_metadata = self._scoped_metadata({"target": target})
            category = "preference"
            stable_key = build_profile_stable_key(category, content)
            self._commit_explicit_write(
                owner="brainstack.profile_items",
                write_class="profile_item",
                source=f"builtin_{action}",
                target=target,
                stable_key=stable_key,
                category=category,
                content=content,
                commit=lambda: self._store.upsert_profile_item(
                    stable_key=stable_key,
                    category=category,
                    content=content,
                    source=f"builtin_{action}",
                    confidence=0.88,
                    metadata=scoped_metadata,
                ),
            )
            return

        self._store.add_continuity_event(
            session_id=self._session_id,
            turn_number=self._turn_counter,
            kind="builtin_memory",
            content=content,
            source=f"on_memory_write:{action}:{target}",
            metadata=self._scoped_metadata({"target": target}),
        )

    def behavior_policy_snapshot(self) -> Dict[str, Any] | None:
        if not self._store:
            return None
        return self._store.get_behavior_policy_snapshot(principal_scope_key=self._principal_scope_key)

    def behavior_policy_trace(self) -> Dict[str, Any] | None:
        if self._last_behavior_policy_trace is None:
            return None
        return json.loads(json.dumps(self._last_behavior_policy_trace, ensure_ascii=True))

    def operating_context_snapshot(self) -> Dict[str, Any] | None:
        if not self._store:
            return None
        return self._store.get_operating_context_snapshot(
            principal_scope_key=self._principal_scope_key,
            session_id=self._session_id,
        )

    def operating_context_trace(self) -> Dict[str, Any] | None:
        if self._last_operating_context_trace is None:
            return None
        return json.loads(json.dumps(self._last_operating_context_trace, ensure_ascii=True))

    def memory_operation_trace(self) -> Dict[str, Any] | None:
        if self._last_memory_operation_trace is None:
            return None
        return json.loads(json.dumps(self._last_memory_operation_trace, ensure_ascii=True))

    def apply_behavior_policy_correction(self, *, rule_id: str, replacement_text: str) -> Dict[str, Any] | None:
        if not self._store:
            return None
        return self._store.apply_behavior_policy_correction(
            principal_scope_key=self._principal_scope_key,
            rule_id=rule_id,
            replacement_text=replacement_text,
            source="behavior_policy_correction:provider",
        )

    def validate_assistant_output(self, content: str) -> Dict[str, Any] | None:
        if not self._store:
            return None
        compiled_policy_record = self._store.get_compiled_behavior_policy(principal_scope_key=self._principal_scope_key)
        compiled_policy = (
            dict(compiled_policy_record.get("policy") or {})
            if isinstance(compiled_policy_record, dict)
            else None
        )
        result = validate_output_against_contract(
            content=content,
            compiled_policy=compiled_policy,
        )
        trace = dict(self._last_behavior_policy_trace or {})
        trace["final_output_validation"] = {
            "surface": "final_output_validation",
            "applied": bool(result.get("applied")),
            "changed": bool(result.get("changed")),
            "repair_count": len(list(result.get("repairs") or [])),
            "remaining_violation_count": len(list(result.get("remaining_violations") or [])),
            "contract": dict(result.get("contract") or {}),
        }
        self._last_behavior_policy_trace = trace
        return result

    def shutdown(self) -> None:
        worker_finished = self._wait_for_tier2_worker(timeout=self._tier2_timeout_seconds + 2.0)
        if not worker_finished:
            logger.error("Refusing to reset Brainstack runtime state while the Tier-2 worker is still running.")
            return
        if not self._ensure_explicit_write_barrier_clear(surface="shutdown"):
            return
        if self._store:
            self._store.close()
            self._store = None
        self._reset_session_runtime_state()

    def _record_tier2_batch_result(self, result: Dict[str, Any]) -> None:
        self._last_tier2_batch_result = dict(result)
        self._tier2_batch_history.append(dict(result))
        if len(self._tier2_batch_history) > 256:
            self._tier2_batch_history = self._tier2_batch_history[-256:]

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

    def _run_tier2_batch(self, *, session_id: str, turn_number: int, trigger_reason: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "session_id": session_id,
            "turn_number": int(turn_number or 0),
            "trigger_reason": trigger_reason,
            "transcript_turn_numbers": [],
            "transcript_ids": [],
            "transcript_count": 0,
            "json_parse_status": "not_run",
            "parse_context": "",
            "extracted_counts": {},
            "action_counts": {},
            "writes_performed": 0,
            "status": "not_run",
        }
        if not self._store:
            return result
        transcript_rows = [
            row
            for row in reversed(self._store.recent_transcript(session_id=session_id, limit=self._tier2_transcript_limit))
            if str(row.get("kind", "")) == "turn"
        ]
        result["transcript_turn_numbers"] = [int(row.get("turn_number") or 0) for row in transcript_rows]
        result["transcript_ids"] = [int(row["id"]) for row in transcript_rows if row.get("id") is not None]
        result["transcript_count"] = len(transcript_rows)
        if not transcript_rows:
            result["status"] = "skipped_no_transcript"
            self._record_tier2_batch_result(result)
            return result
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
        extracted_meta = extracted.get("_meta") if isinstance(extracted, dict) else {}
        result["json_parse_status"] = str((extracted_meta or {}).get("json_parse_status") or "unknown")
        result["parse_context"] = str((extracted_meta or {}).get("parse_context") or "")
        result["raw_payload_preview"] = str((extracted_meta or {}).get("raw_payload_preview") or "")
        result["raw_payload_tail"] = str((extracted_meta or {}).get("raw_payload_tail") or "")
        result["raw_payload_length"] = int((extracted_meta or {}).get("raw_payload_length") or 0)
        extracted_counts = {
            "profile_items": len(list(extracted.get("profile_items", []) or [])),
            "states": len(list(extracted.get("states", []) or [])),
            "relations": len(list(extracted.get("relations", []) or [])),
            "inferred_relations": len(list(extracted.get("inferred_relations", []) or [])),
            "typed_entities": len(list(extracted.get("typed_entities", []) or [])),
            "temporal_events": len(list(extracted.get("temporal_events", []) or [])),
            "decisions": len(list(extracted.get("decisions", []) or [])),
            "continuity_summary_present": 1 if str(extracted.get("continuity_summary") or "").strip() else 0,
        }
        result["extracted_counts"] = extracted_counts
        temporal_event_samples: List[Dict[str, Any]] = []
        for event in list(extracted.get("temporal_events", []) or [])[:6]:
            if not isinstance(event, dict):
                continue
            temporal_event_samples.append(
                {
                    "turn_number": int(event.get("turn_number") or 0),
                    "content": str(event.get("content") or "").strip(),
                }
            )
        result["temporal_event_samples"] = temporal_event_samples
        typed_entity_samples: List[Dict[str, Any]] = []
        for entity in list(extracted.get("typed_entities", []) or [])[:4]:
            if not isinstance(entity, dict):
                continue
            typed_entity_samples.append(
                {
                    "turn_number": int(entity.get("turn_number") or 0),
                    "name": str(entity.get("name") or "").strip(),
                    "entity_type": str(entity.get("entity_type") or "").strip(),
                    "attributes": dict(entity.get("attributes") or {}),
                }
            )
        result["typed_entity_samples"] = typed_entity_samples
        reconcile_report = reconcile_tier2_candidates(
            self._store,
            session_id=session_id,
            turn_number=turn_number,
            source=f"tier2:{trigger_reason}",
            extracted=extracted,
            metadata=self._scoped_metadata({
                "batch_reason": trigger_reason,
                "transcript_ids": [int(row["id"]) for row in transcript_rows if row.get("id") is not None],
            }),
        )
        action_counts: Dict[str, int] = {}
        writes_performed = 0
        for action in reconcile_report.get("actions", []):
            action_name = str(action.get("action") or "UNKNOWN")
            action_counts[action_name] = action_counts.get(action_name, 0) + 1
            if action_name != "NONE":
                writes_performed += 1
        result["action_counts"] = action_counts
        result["writes_performed"] = writes_performed
        result["status"] = "ok"
        self._record_tier2_batch_result(result)
        return result
