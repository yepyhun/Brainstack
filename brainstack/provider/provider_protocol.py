"""Runtime bridge for behavior-preserving provider mixins."""

from __future__ import annotations

from typing import Any


class ProviderRuntimeBase:
    """Mixin self-type bridge for BrainstackMemoryProvider slices."""

    _config: dict[str, Any]
    _lock: Any
    _last_behavior_policy_trace: Any
    _last_graph_ingress_trace: Any
    _last_maintenance_receipt: Any
    _last_memory_authority_debug: Any
    _last_memory_operation_trace: Any
    _last_operating_context_trace: Any
    _last_prefetch_channels: Any
    _last_prefetch_debug: Any
    _last_prefetch_policy: Any
    _last_prefetch_routing: Any
    _last_tier2_batch_result: Any
    _last_tier2_schedule: Any
    _last_turn_monotonic: Any
    _last_write_receipt: Any
    _pending_explicit_write_count: int
    _pending_tier2_turns: int
    _principal_scope: dict[str, str]
    _principal_scope_key: str
    _recent_user_messages: list[str]
    _route_resolver_override: Any
    _session_id: str
    _store: Any
    _tier2_batch_history: list[dict[str, Any]]
    _tier2_followup_requested: bool
    _tier2_lock: Any
    _tier2_running: bool
    _tier2_thread: Any
    _turn_counter: int
    _user_timezone: Any
    _write_receipt_counter: int

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(name)
