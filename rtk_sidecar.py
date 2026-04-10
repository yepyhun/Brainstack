from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from tools.budget_config import BudgetConfig, DEFAULT_BUDGET
from tools.tool_result_storage import PERSISTED_OUTPUT_TAG


DEFAULT_MODELS: Dict[str, Dict[str, Any]] = {
    "balanced": {
        "default_result_size": 60_000,
        "turn_budget": 120_000,
        "preview_size": 1_000,
        "tool_overrides": {
            "web_search": 25_000,
            "terminal": 25_000,
        },
    },
    "aggressive": {
        "default_result_size": 40_000,
        "turn_budget": 80_000,
        "preview_size": 800,
        "tool_overrides": {
            "web_search": 18_000,
            "terminal": 18_000,
        },
    },
}


@dataclass(frozen=True)
class RTKSidecarConfig:
    enabled: bool = False
    mode: str = "off"
    budget: BudgetConfig = field(default_factory=lambda: DEFAULT_BUDGET)


@dataclass
class RTKSidecarStats:
    total_input_chars: int = 0
    total_output_chars: int = 0
    total_chars_saved: int = 0
    persisted_results: int = 0
    truncated_results: int = 0
    budget_enforcements: int = 0

    def record_result(self, original: str, final: str) -> None:
        original_len = len(original or "")
        final_len = len(final or "")
        self.total_input_chars += original_len
        self.total_output_chars += final_len
        self.total_chars_saved += max(0, original_len - final_len)
        lowered = final.lower()
        if PERSISTED_OUTPUT_TAG in final:
            self.persisted_results += 1
        elif "[truncated:" in lowered:
            self.truncated_results += 1

    def record_turn_budget_effect(self, before_total: int, after_total: int) -> None:
        if after_total < before_total:
            self.budget_enforcements += 1
            self.total_chars_saved += before_total - after_total


def build_rtk_sidecar_config(agent_config: Dict[str, Any] | None) -> RTKSidecarConfig:
    sidecars = (agent_config or {}).get("sidecars", {})
    raw = sidecars.get("rtk", {}) if isinstance(sidecars, dict) else {}
    enabled = bool(raw.get("enabled", False))
    if not enabled:
        return RTKSidecarConfig()

    mode = str(raw.get("mode", "balanced")).strip().lower() or "balanced"
    profile = DEFAULT_MODELS.get(mode, DEFAULT_MODELS["balanced"])

    default_result_size = int(raw.get("default_result_size", profile["default_result_size"]))
    turn_budget = int(raw.get("turn_budget", profile["turn_budget"]))
    preview_size = int(raw.get("preview_size", profile["preview_size"]))
    tool_overrides = dict(profile["tool_overrides"])
    raw_overrides = raw.get("tool_overrides", {})
    if isinstance(raw_overrides, dict):
        for key, value in raw_overrides.items():
            try:
                tool_overrides[str(key)] = int(value)
            except (TypeError, ValueError):
                continue

    budget = BudgetConfig(
        default_result_size=default_result_size,
        turn_budget=turn_budget,
        preview_size=preview_size,
        tool_overrides=tool_overrides,
    )
    return RTKSidecarConfig(enabled=True, mode=mode, budget=budget)
