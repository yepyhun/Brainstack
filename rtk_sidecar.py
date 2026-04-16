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
    normalized_results: int = 0
    normalization_chars_saved: int = 0
    persisted_results: int = 0
    truncated_results: int = 0
    budget_enforcements: int = 0

    def record_preprocessing_effect(self, original: str, normalized: str) -> None:
        original_len = len(original or "")
        normalized_len = len(normalized or "")
        if normalized_len < original_len:
            self.normalized_results += 1
            self.normalization_chars_saved += original_len - normalized_len

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


def _looks_structured_payload(content: str) -> bool:
    stripped = content.lstrip()
    if not stripped:
        return False
    if PERSISTED_OUTPUT_TAG in content:
        return True
    return stripped.startswith("{") or stripped.startswith("[")


def maybe_preprocess_tool_result(content: str, config: RTKSidecarConfig) -> str:
    """Apply a tiny, plain-text-safe cleanup before persistence/truncation.

    This stays intentionally conservative:
    - do nothing when the sidecar is disabled
    - do nothing for structured payloads
    - collapse repeated blank lines
    - collapse only consecutive exact duplicate lines (3+ run length)
    """

    if not config.enabled or not content:
        return content
    if ("\n" not in content and "\r" not in content) or _looks_structured_payload(content):
        return content

    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    compacted: list[str] = []
    index = 0
    pending_blank = False

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            if not pending_blank:
                compacted.append("")
                pending_blank = True
            index += 1
            continue

        pending_blank = False
        run_length = 1
        while index + run_length < len(lines) and lines[index + run_length] == line:
            run_length += 1

        if run_length >= 3:
            compacted.append(line)
            compacted.append(f"[x{run_length - 1} repeats omitted]")
        else:
            compacted.extend([line] * run_length)
        index += run_length

    candidate = "\n".join(compacted)
    if content.endswith("\n") and not candidate.endswith("\n"):
        candidate += "\n"
    return candidate if len(candidate) < len(content) else content


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
