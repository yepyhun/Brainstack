"""Compression pressure classification for Hermes sessions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


SCHEMA_VERSION = "brainstack.compression_pressure.v1"


@dataclass(frozen=True)
class CompressionPressureVerdict:
    schema: str
    verdict: str
    reason_codes: tuple[str, ...]
    pressure_tokens_est: int
    preflight_events: int
    failure_lines: int
    success_lines: int
    fallback_required: bool
    recommended_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reason_codes"] = list(self.reason_codes)
        data["recommended_actions"] = list(self.recommended_actions)
        return data


def classify_compression_pressure(
    accounting_report: Mapping[str, Any],
    *,
    warning_tokens: int = 180_000,
    critical_tokens: int = 240_000,
) -> CompressionPressureVerdict:
    compression = dict(accounting_report.get("compression") or {})
    totals = dict(accounting_report.get("totals") or {})
    pressure_tokens = int(compression.get("preflight_max_tokens") or totals.get("tokens_est") or 0)
    preflight_events = int(compression.get("preflight_events") or 0)
    failure_lines = int(compression.get("failure_lines") or 0)
    success_lines = int(compression.get("success_lines") or 0)

    reasons: list[str] = []
    actions: list[str] = []
    if pressure_tokens >= critical_tokens:
        reasons.append("CONTEXT_PRESSURE_CRITICAL")
        actions.append("externalize_large_tool_outputs_before_preflight")
    elif pressure_tokens >= warning_tokens:
        reasons.append("CONTEXT_PRESSURE_WARNING")
        actions.append("queue_context_pressure_compaction")
    if failure_lines and not success_lines:
        reasons.append("COMPRESSION_FAILURE_WITHOUT_SUCCESS")
        actions.append("enable_deterministic_fallback_summary")
    elif failure_lines:
        reasons.append("COMPRESSION_FAILURES_OBSERVED")
        actions.append("surface_compression_degraded_health")
    if preflight_events and pressure_tokens >= warning_tokens:
        actions.append("run_context_accounting_before_next_release_claim")

    if "COMPRESSION_FAILURE_WITHOUT_SUCCESS" in reasons or "CONTEXT_PRESSURE_CRITICAL" in reasons:
        verdict = "critical"
    elif reasons:
        verdict = "degraded"
    else:
        verdict = "healthy"
    return CompressionPressureVerdict(
        schema=SCHEMA_VERSION,
        verdict=verdict,
        reason_codes=tuple(reasons),
        pressure_tokens_est=pressure_tokens,
        preflight_events=preflight_events,
        failure_lines=failure_lines,
        success_lines=success_lines,
        fallback_required=bool(failure_lines and not success_lines),
        recommended_actions=tuple(dict.fromkeys(actions)),
    )

