#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack import BrainstackMemoryProvider  # noqa: E402


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=True)
        return value
    except TypeError:
        return str(value)


def _provider(db_path: Path, *, runtime: str = "internal_extractor") -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(db_path),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "tier2_runtime": runtime,
            "tier2_hindsight_llm_provider": "hermes_managed",
            "tier2_hindsight_llm_model": "gpt-5.5",
        }
    )
    provider.initialize(
        "tier2-truthful-diagnostics",
        platform="verification",
        user_id="public-safe-user",
        agent_identity="brainstack-verifier",
        agent_workspace="verification",
    )
    return provider


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-tier2-truthful-") as tmp:
        db_path = Path(tmp) / "brainstack.sqlite3"
        provider = _provider(db_path, runtime="internal_extractor")
        try:
            assert provider._store is not None
            provider._store.record_tier2_run_result(
                {
                    "run_id": "verify-failed-tier2-run",
                    "session_id": "tier2-truthful-diagnostics",
                    "turn_number": 1,
                    "trigger_reason": "verification",
                    "request_status": "failed",
                    "json_parse_status": "not_run",
                    "status": "failed",
                    "transcript_count": 1,
                    "extracted_counts": {},
                    "action_counts": {},
                    "writes_performed": 0,
                    "no_op_reasons": [],
                    "error_reason": "redacted verification failure detail",
                    "duration_ms": 1,
                }
            )
            failed_doctor = provider.memory_kernel_doctor(strict=True)
            failed_stats = json.loads(provider.handle_tool_call("brainstack_stats", {"strict": True}))
        finally:
            provider.shutdown()

        unbound_provider = _provider(db_path, runtime="hindsight_public_api_bridge")
        try:
            route = unbound_provider.lifecycle_status()["tier2_runtime_route"]
            unbound_doctor = unbound_provider.memory_kernel_doctor(strict=True)
        finally:
            unbound_provider.shutdown()

    failed_tier2 = failed_doctor.get("capabilities", {}).get("tier2", {})
    latest = failed_tier2.get("latest_persistent_run", {})
    unbound_tier2 = unbound_doctor.get("capabilities", {}).get("tier2", {})
    issues: list[str] = []
    if failed_doctor.get("verdict") != "fail":
        issues.append("failed_persisted_run_did_not_fail_strict_doctor")
    if failed_tier2.get("reason_code") != "TIER2_PERSISTED_RUN_FAILED":
        issues.append("failed_persisted_run_reason_code_missing")
    if "error_reason" in latest:
        issues.append("raw_error_reason_leaked")
    if failed_stats.get("doctor", {}).get("capabilities", {}).get("tier2", {}).get("reason_code") != "TIER2_PERSISTED_RUN_FAILED":
        issues.append("stats_did_not_expose_tier2_failed_reason_code")
    if route.get("binding_status") != "configured_unbound":
        issues.append("hindsight_route_not_marked_configured_unbound")
    if unbound_tier2.get("reason_code") != "TIER2_RUNTIME_CONFIGURED_UNBOUND":
        issues.append("unbound_hindsight_route_did_not_degrade_doctor")

    return {
        "schema": "brainstack.tier2_truthful_diagnostics_verification.v1",
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "issues": issues,
        "failed_run_probe": {
            "doctor_verdict": failed_doctor.get("verdict"),
            "tier2_status": failed_tier2.get("status"),
            "tier2_reason_code": failed_tier2.get("reason_code"),
            "stats_status": failed_stats.get("status"),
            "latest_persistent_run": _jsonable(latest),
        },
        "unbound_runtime_probe": {
            "route_binding_status": route.get("binding_status"),
            "route_binding_reason_code": route.get("binding_reason_code"),
            "doctor_verdict": unbound_doctor.get("verdict"),
            "tier2_status": unbound_tier2.get("status"),
            "tier2_reason_code": unbound_tier2.get("reason_code"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Tier2 runtime binding and truthful diagnostics.")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
