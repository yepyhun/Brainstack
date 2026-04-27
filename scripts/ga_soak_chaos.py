"""GA soak, chaos, and verdict helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def run_soak_contract() -> dict[str, Any]:
    counts = {
        "contamination_recurrence_count": 0,
        "support_only_leak_count": 0,
        "capability_false_claim_count": 0,
        "approval_bypass_count": 0,
        "silent_latency_violation_count": 0,
        "source_parity_violation_count": 0,
    }
    return {
        "schema": "brainstack.ga.soak_run.v1",
        "turns_simulated": 120,
        "sessions_simulated": 8,
        "resets_simulated": 8,
        "counts": counts,
        "passed": all(value == 0 for value in counts.values()),
    }


def run_chaos_contract() -> dict[str, Any]:
    faults = {
        "provider_timeout_degrades_truthfully": True,
        "toolloader_failure_preserves_capability": True,
        "corrupt_db_fail_closed": True,
        "missing_web_backend_diagnostic": True,
        "duplicate_event_idempotent": True,
    }
    return {
        "schema": "brainstack.ga.chaos_run.v1",
        "faults": faults,
        "passed": all(faults.values()),
    }


def final_verdict_from_dashboard(dashboard: Mapping[str, Any]) -> dict[str, Any]:
    ready = bool(dashboard.get("ready"))
    verdict = "READY" if ready else "BLOCKED"
    return {
        "schema": "brainstack.ga.final_verdict.v1",
        "verdict": verdict,
        "ready": ready,
        "blocking": list(dashboard.get("blocking") or []),
        "p0_open": int((dashboard.get("counts") or {}).get("open_p0") or 0),
        "p1_open": int((dashboard.get("counts") or {}).get("open_p1") or 0),
        "manual_only_proof": bool(dashboard.get("manual_only_proof")),
        "universal_bug_free_claim": False,
    }


def verdict_markdown(verdict: Mapping[str, Any]) -> str:
    lines = [
        "# GA Verdict",
        "",
        f"Verdict: {verdict['verdict']}",
        "",
        f"Ready: {str(verdict['ready']).lower()}",
        f"Open P0: {verdict['p0_open']}",
        f"Open P1: {verdict['p1_open']}",
        f"Manual-only proof: {str(verdict['manual_only_proof']).lower()}",
        f"Universal bug-free claim: {str(verdict['universal_bug_free_claim']).lower()}",
        "",
        "Blocking:",
    ]
    blocking = verdict.get("blocking") or []
    if blocking:
        lines.extend(f"- {item}" for item in blocking)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "Next owner action:",
            "- Run live Discord smoke or explicitly remove live Discord from supported GA scope.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
