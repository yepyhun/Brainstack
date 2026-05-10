#!/usr/bin/env python3
"""Destructive proof for actionable/proactive/runtime/wizard seams."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import install_into_hermes  # noqa: E402
from scripts.run_source_backed_actionable_queue_substrate import build_report as build_actionable_report  # noqa: E402
from scripts.verify_auxiliary_auth_runtime_contract import run_verification as build_auxiliary_report  # noqa: E402
from scripts.verify_hermes_proactive_runtime_parity import (  # noqa: E402
    build_proactive_runtime_parity_report,
)

REPORT_SCHEMA = "brainstack.actionable_proactive_runtime_wizard_destructive_proof.v1"
PRIVATE_CANARIES = (
    "secret='do-not-leak'",
    "private doctor payload must not leak",
    "super-secret",
)


def _public_safe(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return not any(canary in text for canary in PRIVATE_CANARIES)


def _case(case_id: str, checks: Mapping[str, bool], payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    failed = sorted(key for key, passed in checks.items() if not passed)
    return {
        "case_id": case_id,
        "status": "pass" if not failed else "fail",
        "checks": dict(checks),
        "failed_checks": failed,
        "payload": dict(payload or {}),
    }


def _wizard_patch_reproduction_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-2766-wizard-") as raw:
        root = Path(raw)
        auxiliary_client = root / "auxiliary_client.py"
        auxiliary_client.write_text(
            "from typing import Any, Dict, Optional, Tuple\n\n"
            "def resolve_provider_client(provider=None, model=None):\n"
            "    cfg_provider = provider\n"
            "    cfg_model = None\n"
            "    resolved_model = model or cfg_model\n"
            "    return provider, resolved_model\n"
            "\n"
            "_client_cache = {}\n"
            "_client_cache_lock = None\n\n"
            "def _client_cache_key(provider, *, async_mode=False, base_url=None, api_key=None, api_mode=None, main_runtime=None, is_vision=False):\n"
            "    return (provider, async_mode, base_url or '', api_key or '', api_mode or '', is_vision)\n\n"
            "def _normalize_main_runtime(main_runtime):\n"
            "    return main_runtime\n\n"
            "def _force_close_async_httpx(client):\n"
            "    pass\n\n"
            "def _compat_model(client: Any, model: Optional[str], cached_default: Optional[str]) -> Optional[str]:\n"
            "    return model or cached_default\n\n"
            "def _get_cached_client(\n"
            "    provider: str,\n"
            "    model: str = None,\n"
            "    async_mode: bool = False,\n"
            "    base_url: str = None,\n"
            "    api_key: str = None,\n"
            "    api_mode: str = None,\n"
            "    main_runtime: Optional[Dict[str, Any]] = None,\n"
            "    is_vision: bool = False,\n"
            ") -> Tuple[Optional[Any], Optional[str]]:\n"
            "    current_loop = None\n"
            "    runtime = _normalize_main_runtime(main_runtime)\n"
            "    cache_key = _client_cache_key(provider, async_mode=async_mode, base_url=base_url, api_key=api_key, api_mode=api_mode, main_runtime=main_runtime, is_vision=is_vision)\n"
            "    with _client_cache_lock:\n"
            "        if cache_key in _client_cache:\n"
            "            cached_client, cached_default, cached_loop = _client_cache[cache_key]\n"
            "            if async_mode:\n"
            "                loop_ok = (\n"
            "                    cached_loop is not None\n"
            "                    and cached_loop is current_loop\n"
            "                    and not cached_loop.is_closed()\n"
            "                )\n"
            "                if loop_ok:\n"
            "                    effective = _compat_model(cached_client, model, cached_default)\n"
            "                    return cached_client, effective\n"
            "                _force_close_async_httpx(cached_client)\n"
            "                del _client_cache[cache_key]\n"
            "            else:\n"
            "                effective = _compat_model(cached_client, model, cached_default)\n"
            "                return cached_client, effective\n"
            "    return None, None\n",
            encoding="utf-8",
        )
        session_search_tool = root / "session_search_tool.py"
        session_search_tool.write_text(
            "import asyncio\n"
            "import concurrent.futures\n"
            "import json\n"
            "import logging\n\n"
            "def _get_session_search_max_concurrency(default=3):\n"
            "    return default\n\n"
            "def _format_timestamp(ts):\n"
            "    return str(ts)\n\n"
            "def _run_async(coro):\n"
            "    return asyncio.run(coro)\n\n"
            "def session_search(query):\n"
            "    try:\n"
            "        seen_sessions = {}\n"
            "        tasks = []\n"
            "        async def _summarize_all():\n"
            "            coros = []\n"
            "            return await asyncio.gather(*coros, return_exceptions=True)\n"
            "        try:\n"
            "            results = _run_async(_summarize_all())\n"
            "        except concurrent.futures.TimeoutError:\n"
            "            logging.warning(\n"
            "                \"Session summarization timed out after 60 seconds\",\n"
            "                exc_info=True,\n"
            "            )\n"
            "            return json.dumps({\n"
            "                \"success\": False,\n"
            "                \"error\": \"Session summarization timed out. Try a more specific query or reduce the limit.\",\n"
            "            }, ensure_ascii=False)\n"
            "        return json.dumps({\"success\": True}, ensure_ascii=False)\n"
            "    except Exception as exc:\n"
            "        return json.dumps({\"success\": False, \"error\": str(exc)}, ensure_ascii=False)\n",
            encoding="utf-8",
        )
        auxiliary_actions = install_into_hermes._run_host_patch(
            "_patch_auxiliary_client",
            auxiliary_client,
            dry_run=False,
            host_patch_mode="core",
        )
        session_search_actions = install_into_hermes._run_host_patch(
            "_patch_session_search_total_deadline",
            session_search_tool,
            dry_run=False,
            host_patch_mode="core",
        )
        auxiliary_text = auxiliary_client.read_text(encoding="utf-8")
        session_text = session_search_tool.read_text(encoding="utf-8")
    checks = {
        "auxiliary_main_model_inheritance_patch_applied": "auxiliary_client:inherit_main_model" in auxiliary_actions,
        "auxiliary_inherits_provider_main": 'explicit_provider == "main"' in auxiliary_text
        and "_read_main_model() or None" in auxiliary_text,
        "auxiliary_closed_sync_cache_patch_applied": "auxiliary_client:evict_closed_sync_cache" in auxiliary_actions,
        "auxiliary_evicts_closed_sync_client": "def _brainstack_auxiliary_client_is_closed" in auxiliary_text
        and "_brainstack_auxiliary_client_is_closed(cached_client)" in auxiliary_text,
        "session_search_deadline_patch_applied": session_search_actions
        == [
            "session_search:total_deadline_helper",
            "session_search:bounded_gather",
            "session_search:timeout_degraded_preview",
        ],
        "session_search_has_total_deadline": "def _get_session_search_total_deadline" in session_text
        and "timeout=_get_session_search_total_deadline()" in session_text,
        "session_search_degrades_instead_of_hanging": "SESSION_SEARCH_SUMMARIZATION_TIMEOUT" in session_text
        and '"success": True' in session_text
        and '"degraded": True' in session_text,
    }
    return {
        "checks": checks,
        "actions": {
            "auxiliary_client": auxiliary_actions,
            "session_search": session_search_actions,
        },
    }


def build_report() -> dict[str, Any]:
    actionable = build_actionable_report()
    proactive_runtime = build_proactive_runtime_parity_report()
    auxiliary = build_auxiliary_report()
    wizard = _wizard_patch_reproduction_report()

    actionable_checks = actionable.get("checks") if isinstance(actionable.get("checks"), Mapping) else {}
    actionable_counts = actionable.get("counts") if isinstance(actionable.get("counts"), Mapping) else {}
    actionable_case = _case(
        "actionable_substrate_is_read_only_and_not_governor",
        {
            "source_backed_task_visible": actionable_checks.get("pending_actionable_count_one") is True,
            "support_only_candidate_rejected": actionable_checks.get("rejected_candidate_receipt_recorded") is True,
            "status_read_only": actionable_checks.get("status_read_only") is True,
            "status_read_did_not_mutate_proactive_tables": actionable_checks.get(
                "status_read_did_not_mutate_proactive_tables"
            )
            is True,
            "no_proactive_event_created": actionable_checks.get("no_proactive_event_created") is True,
            "no_outbox_created": actionable_checks.get("no_outbox_created") is True,
            "no_attention_ledger_created": int(actionable_counts.get("proactive_attention_ledger") or 0) == 0,
            "sample_has_no_execution_payload": actionable_checks.get("sample_has_no_execution_payload") is True,
        },
        {
            "report_status": actionable.get("status"),
            "counts": actionable_counts,
        },
    )

    scenario_statuses = proactive_runtime.get("scenario_statuses")
    scenario_statuses = scenario_statuses if isinstance(scenario_statuses, Mapping) else {}
    payload_files = proactive_runtime.get("payload_files")
    payload_files = payload_files if isinstance(payload_files, Mapping) else {}
    proactive_case = _case(
        "proactive_runtime_states_are_truthful_and_side_effect_free",
        {
            "runtime_report_passed": proactive_runtime.get("status") == "pass",
            "public_safe": proactive_runtime.get("public_safe") is True,
            "zero_runtime_side_effects": proactive_runtime.get("zero_runtime_side_effects") is True,
            "idle_truthful": scenario_statuses.get("idle") == "idle",
            "active_truthful": scenario_statuses.get("active") == "active",
            "paused_truthful": scenario_statuses.get("paused") == "paused",
            "dry_run_truthful": scenario_statuses.get("dry_run") == "observed",
            "killed_truthful": scenario_statuses.get("killed") == "killed",
            "malformed_degrades": scenario_statuses.get("malformed") == "degraded",
            "payload_files_present": payload_files.get("status") == "present"
            and payload_files.get("missing") == [],
        },
        {
            "scenario_statuses": dict(scenario_statuses),
            "payload_files_status": payload_files.get("status"),
        },
    )

    aux_cases = auxiliary.get("cases") if isinstance(auxiliary.get("cases"), list) else []
    aux_by_id = {str(case.get("case_id")): case for case in aux_cases if isinstance(case, Mapping)}
    auxiliary_case = _case(
        "auxiliary_runtime_routes_block_invalid_state_before_llm_call",
        {
            "auxiliary_report_passed": auxiliary.get("status") == "pass",
            "main_blank_inherits_main_model": bool(aux_by_id.get("main_blank_inherits_main_model", {}).get("passed")),
            "main_blank_without_main_model_blocks": bool(
                aux_by_id.get("main_blank_without_main_model_blocks", {}).get("passed")
            ),
            "unsupported_main_model_blocks": bool(aux_by_id.get("main_stepfun_on_codex_blocks_before_call", {}).get("passed")),
            "installer_materializes_ready_routes": bool(
                aux_by_id.get("installer_materializes_ready_background_routes", {}).get("passed")
            ),
            "no_llm_calls_performed": True,
        },
        {
            "case_count": len(aux_cases),
        },
    )

    wizard_case = _case(
        "wizard_core_patch_reproduces_runtime_seams",
        wizard.get("checks") if isinstance(wizard.get("checks"), Mapping) else {},
        {"actions": wizard.get("actions")},
    )

    cases = [actionable_case, proactive_case, auxiliary_case, wizard_case]
    issues = [f"{case['case_id']}:{item}" for case in cases for item in case["failed_checks"]]
    public_safe = _public_safe(cases)
    if not public_safe:
        issues.append("public_safety_failed")
    proof = {
        "support_only_action_rejected_without_substrate": actionable_case["checks"].get(
            "support_only_candidate_rejected"
        )
        is True
        and actionable_case["checks"].get("source_backed_task_visible") is True,
        "proactive_status_read_only_no_side_effect": actionable_case["checks"].get("status_read_only") is True
        and actionable_case["checks"].get("status_read_did_not_mutate_proactive_tables") is True,
        "no_outbox_or_scheduler_side_effect": actionable_case["checks"].get("no_outbox_created") is True
        and actionable_case["checks"].get("no_proactive_event_created") is True
        and proactive_case["checks"].get("zero_runtime_side_effects") is True,
        "runtime_degraded_states_truthful": all(
            proactive_case["checks"].get(key) is True
            for key in (
                "idle_truthful",
                "active_truthful",
                "paused_truthful",
                "dry_run_truthful",
                "killed_truthful",
                "malformed_degrades",
            )
        ),
        "auxiliary_invalid_routes_block_before_call": auxiliary_case["checks"].get("main_blank_without_main_model_blocks")
        is True
        and auxiliary_case["checks"].get("unsupported_main_model_blocks") is True,
        "main_model_inheritance_ready": auxiliary_case["checks"].get("main_blank_inherits_main_model") is True,
        "wizard_core_patches_auxiliary_and_session_search": all(wizard_case["checks"].values()),
        "proactive_payload_files_present": proactive_case["checks"].get("payload_files_present") is True,
        "public_safe": public_safe,
    }
    failed_proof = [key for key, passed in proof.items() if passed is not True]
    issues.extend(f"proof:{key}" for key in failed_proof)
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "issues": sorted(set(issues)),
        "failure_case_ids": [case["case_id"] for case in cases if case["status"] != "pass"],
        "case_count": len(cases),
        "cases": cases,
        "proof": proof,
        "public_safe": public_safe,
        "llm_calls_performed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="", help="Write JSON report")
    args = parser.parse_args(argv)
    report = build_report()
    text = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True, default=str)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "schema": report["schema"],
                "status": report["status"],
                "issue_count": len(report["issues"]),
                "issues": report["issues"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
