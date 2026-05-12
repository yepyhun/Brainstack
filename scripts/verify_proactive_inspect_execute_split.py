#!/usr/bin/env python3
"""Verify proactive inspect/execute split and foreground wait guard."""

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

from scripts import install_into_hermes  # noqa: E402
from scripts.run_actionable_proactive_runtime_wizard_destructive_proof import build_report as build_actionable_report  # noqa: E402


REPORT_SCHEMA = "brainstack.proactive_inspect_execute_split.v1"


def _fake_run_agent_module(path: Path) -> None:
    path.write_text(
        '''
class AIAgent:
    def _validate_external_memory_final_response(
        self,
        *,
        original_user_message: Any,
        final_response: Any,
        interrupted: bool,
    ) -> Any:
        return final_response

    def _replace_last_assistant_response_content(
        self,
        messages: Any,
        conversation_history: Any,
        final_response: Any,
    ) -> None:
        pass

    def _invoke_tool(self, function_name: str, function_args: dict, effective_task_id: str, tool_call_id: Any = None, messages: list = None) -> str:
        block_message = None
        if block_message is not None:
            return json.dumps({"error": block_message}, ensure_ascii=False)
        return "{}"

    def _execute_tool_calls_sequential(self, assistant_message, messages: list, effective_task_id: str, api_call_count: int = 0) -> None:
        for tool_call in assistant_message.tool_calls:
            function_name = "terminal"
            function_args = {}
            _block_msg = None
            if _block_msg is not None:
                # Tool blocked by plugin policy — skip counter resets.
                # Execution is handled below in the tool dispatch chain.
                pass
            else:
                pass

    def _loop(self, assistant_message, finish_reason, messages):
                    final_response = assistant_message.content or ""

                    # Fix: unmute output when entering the no-tool-call branch
                    # so the user can see empty-response warnings and recovery
                    self._mute_post_response = False

    def run(self):
        if final_response and not interrupted:
            final_response = self._validate_external_memory_final_response(
                original_user_message=original_user_message,
                final_response=final_response,
                interrupted=interrupted,
            )
            self._replace_last_assistant_response_content(messages, conversation_history, final_response)
''',
        encoding="utf-8",
    )


def _patch_proof(tmp: Path) -> dict[str, Any]:
    module = tmp / "run_agent.py"
    _fake_run_agent_module(module)
    applied = install_into_hermes._patch_run_agent_terminal_final_guard_seam(module, dry_run=False)
    text = module.read_text(encoding="utf-8")
    return {
        "applied": applied,
        "has_foreground_wait_helper": "def _terminal_foreground_wait_block_message(" in text,
        "has_foreground_wait_message": "Foreground orchestration wait blocked" in text,
        "concurrent_checks_foreground_wait": "block_message = self._terminal_foreground_wait_block_message(function_name, function_args)" in text,
        "sequential_checks_foreground_wait": "_block_msg = self._terminal_foreground_wait_block_message(function_name, function_args)" in text,
        "still_has_url_guard": "_terminal_url_fetch_block_message(function_name, function_args, messages)" in text,
    }


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-proactive-inspect-execute-") as raw:
        patch = _patch_proof(Path(raw))
    actionable = build_actionable_report()
    action_proof = actionable.get("proof") if isinstance(actionable.get("proof"), dict) else {}
    proof = {
        "proactive_status_read_only_no_side_effect": action_proof.get("proactive_status_read_only_no_side_effect") is True,
        "no_outbox_or_scheduler_side_effect": action_proof.get("no_outbox_or_scheduler_side_effect") is True,
        "foreground_wait_guard_helper_installed": patch["has_foreground_wait_helper"] is True,
        "foreground_wait_guard_message_installed": patch["has_foreground_wait_message"] is True,
        "foreground_wait_guard_concurrent_path": patch["concurrent_checks_foreground_wait"] is True,
        "foreground_wait_guard_sequential_path": patch["sequential_checks_foreground_wait"] is True,
        "url_guard_preserved": patch["still_has_url_guard"] is True,
    }
    issues = sorted(key for key, value in proof.items() if value is not True)
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "read_only": True,
        "issues": issues,
        "proof": proof,
        "patch_applied": patch["applied"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify proactive inspect/execute split and foreground wait guard.")
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
