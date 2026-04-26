"""Brainstack memory plugin — continuity, profile, graph-truth, and corpus substrate."""

from __future__ import annotations

from .provider.runtime import (
    Any,
    BrainstackStore,
    Dict,
    List,
    MemoryProvider,
    _load_plugin_config,
    resolve_user_timezone,
    threading,
)
from .provider.config_lifecycle import ConfigLifecycleMixin
from .provider.explicit_capture import ExplicitCaptureMixin
from .provider.prefetch_sync import PrefetchSyncMixin
from .provider.tools import ProviderToolsMixin
from .provider.ingest_lifecycle import IngestLifecycleMixin
from .provider.inspection import ProviderInspectionMixin
from .provider.tier2_worker import Tier2WorkerMixin

__all__ = ["BrainstackMemoryProvider"]


class BrainstackMemoryProvider(
    ConfigLifecycleMixin,
    ExplicitCaptureMixin,
    PrefetchSyncMixin,
    ProviderToolsMixin,
    IngestLifecycleMixin,
    ProviderInspectionMixin,
    Tier2WorkerMixin,
    MemoryProvider,
):
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
        self._evidence_item_budget = int(self._config.get("evidence_item_budget", 8))
        self._operating_match_limit = int(self._config.get("operating_match_limit", 3))
        self._graph_match_limit = int(self._config.get("graph_match_limit", 6))
        self._corpus_match_limit = int(self._config.get("corpus_match_limit", 4))
        self._corpus_char_budget = int(self._config.get("corpus_char_budget", 700))
        self._corpus_section_max_chars = int(self._config.get("corpus_section_max_chars", 900))
        self._system_prompt_behavior_contract_enabled = bool(
            self._config.get("system_prompt_behavior_contract_enabled", False)
        )
        self._ordinary_packet_behavior_contract_enabled = bool(
            self._config.get("ordinary_packet_behavior_contract_enabled", False)
        )
        self._ordinary_reply_output_validation_enabled = bool(
            self._config.get("ordinary_reply_output_validation_enabled", False)
        )
        self._tier2_session_end_flush_enabled = bool(
            self._config.get("tier2_session_end_flush_enabled", False)
        )
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
        self._last_memory_authority_debug: Dict[str, Any] | None = None
        self._last_behavior_policy_trace: Dict[str, Any] | None = None
        self._last_operating_context_trace: Dict[str, Any] | None = None
        self._last_graph_ingress_trace: Dict[str, Any] | None = None
        self._last_memory_operation_trace: Dict[str, Any] | None = None
        self._last_write_receipt: Dict[str, Any] | None = None
        self._last_tier2_schedule: Dict[str, Any] | None = None
        self._last_tier2_batch_result: Dict[str, Any] | None = None
        self._last_maintenance_receipt: Dict[str, Any] | None = None
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
