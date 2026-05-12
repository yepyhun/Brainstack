#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.background_task_binding import (  # noqa: E402
    CAPTURE_UNDERSTANDING_HERMES_TASK_SLOT,
    QUERY_UNDERSTANDING_HERMES_TASK_SLOT,
    install_default_background_task_bindings,
    resolve_auxiliary_route_readiness,
)


def _case(case_id: str, passed: bool, observed: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "passed": bool(passed),
        "observed": observed,
    }


def run_verification() -> dict[str, Any]:
    valid_main_blank = resolve_auxiliary_route_readiness(
        task_slot="flush_memories",
        provider_label="main",
        model_label="",
        main_provider_label="openai-codex",
        main_model_label="gpt-5.5",
    )
    invalid_main_blank = resolve_auxiliary_route_readiness(
        task_slot="flush_memories",
        provider_label="main",
        model_label="",
        main_provider_label="openai-codex",
        main_model_label="",
    )
    invalid_stepfun = resolve_auxiliary_route_readiness(
        task_slot=CAPTURE_UNDERSTANDING_HERMES_TASK_SLOT,
        provider_label="main",
        model_label="stepfun/step-3.5-flash",
        main_provider_label="openai-codex",
        main_model_label="gpt-5.5",
    )
    installed_config: dict[str, Any] = {
        "model": {"provider": "openai-codex", "default": "gpt-5.5"},
        "plugins": {"brainstack": {}},
        "auxiliary": {
            "flush_memories": {"provider": "main", "model": ""},
            CAPTURE_UNDERSTANDING_HERMES_TASK_SLOT: {"provider": "main", "model": "gpt-5.5"},
            QUERY_UNDERSTANDING_HERMES_TASK_SLOT: {"provider": "main", "model": "gpt-5.5"},
        },
    }
    installed_status = install_default_background_task_bindings(installed_config)
    cases = [
        _case(
            "main_blank_inherits_main_model",
            valid_main_blank.get("status") == "ready"
            and valid_main_blank.get("effective_model_label") == "gpt-5.5",
            valid_main_blank,
        ),
        _case(
            "main_blank_without_main_model_blocks",
            invalid_main_blank.get("status") == "blocked"
            and invalid_main_blank.get("reason_code") == "AUXILIARY_MAIN_MODEL_UNRESOLVED",
            invalid_main_blank,
        ),
        _case(
            "main_stepfun_on_codex_blocks_before_call",
            invalid_stepfun.get("status") == "blocked"
            and invalid_stepfun.get("reason_code") == "AUXILIARY_MODEL_UNSUPPORTED_FOR_PROVIDER",
            invalid_stepfun,
        ),
        _case(
            "installer_materializes_ready_background_routes",
            installed_status.get("tier2_write_allowed") is True
            and dict(installed_status.get("summary") or {}).get("all_required_routes_ready") is True,
            {
                "tier2_write_allowed": installed_status.get("tier2_write_allowed"),
                "summary": dict(installed_status.get("summary") or {}),
            },
        ),
    ]
    issues = [
        {"case_id": case["case_id"], "reason": "case_failed"}
        for case in cases
        if not bool(case.get("passed"))
    ]
    return {
        "schema": "brainstack.auxiliary_auth_runtime_contract_verification.v1",
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "secret_redacted": True,
        "llm_calls_performed": 0,
        "cases": cases,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = run_verification()
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
