from __future__ import annotations

from .provider_protocol import ProviderRuntimeBase
from .runtime import (
    Any,
    BrainstackStore,
    Dict,
    Mapping,
    Path,
    _build_principal_scope,
    _normalize_path,
    get_donor_registry,
    logger,
    resolve_user_timezone,
)

class ConfigLifecycleMixin(ProviderRuntimeBase):
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
            {"key": "evidence_item_budget", "description": "Shared cross-shelf cap for selected evidence rows per turn", "default": "8"},
            {"key": "operating_match_limit", "description": "How many operating-truth items to consider per turn", "default": "3"},
            {"key": "graph_match_limit", "description": "How many graph-truth items to inject per turn", "default": "6"},
            {"key": "corpus_match_limit", "description": "How many corpus sections to consider per turn", "default": "4"},
            {"key": "corpus_char_budget", "description": "Approximate character budget for packed corpus recall", "default": "700"},
            {"key": "corpus_section_max_chars", "description": "Maximum size of an ingested corpus section", "default": "900"},
            {
                "key": "system_prompt_behavior_contract_enabled",
                "description": "Legacy compatibility toggle for archived rule-pack projection; keep disabled for normal runtime",
                "default": "false",
            },
            {
                "key": "ordinary_packet_behavior_contract_enabled",
                "description": "Legacy compatibility toggle for ordinary-turn contract projection; keep disabled",
                "default": "false",
            },
            {
                "key": "ordinary_reply_output_validation_enabled",
                "description": "Legacy compatibility toggle for ordinary-reply validation; keep disabled",
                "default": "false",
            },
            {"key": "user_timezone", "description": "Default timezone for relative task and commitment dates", "default": "UTC"},
            {"key": "tier2_idle_window_seconds", "description": "Idle window before the future Tier-2 batch may be queued", "default": "30"},
            {"key": "tier2_batch_turn_limit", "description": "How many turns may accumulate before the future Tier-2 batch is queued", "default": "5"},
            {"key": "tier2_transcript_limit", "description": "How many recent transcript turns Tier-2 may read per batch", "default": "8"},
            {"key": "tier2_session_end_flush_enabled", "description": "Run synchronous Tier-2 extraction during on_session_end", "default": "false"},
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
        self._last_memory_authority_debug = None
        self._last_behavior_policy_trace = None
        self._last_operating_context_trace = None
        self._last_graph_ingress_trace = None
        self._last_memory_operation_trace = None
        self._last_write_receipt = None
        self._last_tier2_schedule = None
        self._last_tier2_batch_result = None
        self._last_maintenance_receipt = None
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
        self._hermes_home = ""

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
        self._hermes_home = hermes_home
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

    def _scoped_metadata(self, metadata: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        payload = dict(metadata or {})
        if self._user_timezone:
            payload.setdefault("timezone", self._user_timezone)
        if self._principal_scope_key:
            payload.setdefault("principal_scope_key", self._principal_scope_key)
            payload.setdefault("principal_scope", dict(self._principal_scope))
        return payload

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
