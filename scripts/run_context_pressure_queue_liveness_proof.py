#!/usr/bin/env python3
"""Verify background output stays bounded before it reaches chat/model context."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

from scripts import install_into_hermes  # noqa: E402


def _fixture() -> str:
    return '''
import asyncio
import os
import re
import time
from pathlib import Path

def _format_gateway_process_notification(evt: dict) -> "str | None":
    """Format a watch pattern event from completion_queue into a [IMPORTANT:] message."""
    evt_type = evt.get("type", "completion")
    _sid = evt.get("session_id", "unknown")
    _cmd = evt.get("command", "unknown")

    if evt_type == "watch_disabled":
        return f"[IMPORTANT: {evt.get('message', '')}]"

    if evt_type == "watch_match":
        _pat = evt.get("pattern", "?")
        _out = evt.get("output", "")
        _sup = evt.get("suppressed", 0)
        text = (
            f"[IMPORTANT: Background process {_sid} matched "
            f"watch pattern \\"{_pat}\\".\\n"
            f"Command: {_cmd}\\n"
            f"Matched output:\\n{_out}"
        )
        if _sup:
            text += f"\\n({_sup} earlier matches were suppressed by rate limit)"
        text += "]"
        return text

    return None

class GatewayRunner:
    async def _run_process_watcher(self, watcher: dict) -> None:
        session_id = watcher["session_id"]
        while True:
            if session.exited:
                from tools.process_registry import process_registry as _pr_check
                if agent_notify and not _pr_check.is_completion_consumed(session_id):
                    from tools.ansi_strip import strip_ansi
                    _out = strip_ansi(session.output_buffer[-2000:]) if session.output_buffer else ""
                    synth_text = (
                        f"[IMPORTANT: Background process {session_id} completed "
                        f"(exit code {session.exit_code}).\\n"
                        f"Command: {session.command}\\n"
                        f"Output:\\n{_out}]"
                    )

                if should_notify:
                    new_output = session.output_buffer[-1000:] if session.output_buffer else ""
                    message_text = (
                        f"[Background process {session_id} finished with exit code {session.exit_code}~ "
                        f"Here's the final output:\\n{new_output}]"
                    )
                break

            elif has_new_output and notify_mode == "all" and not agent_notify:
                new_output = session.output_buffer[-500:] if session.output_buffer else ""
                message_text = (
                    f"[Background process {session_id} is still running~ "
                    f"New output:\\n{new_output}]"
                )
'''


def build_report() -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="brainstack-context-pressure-") as raw:
        base = Path(raw)
        module = base / "gateway_run.py"
        module.write_text(_fixture(), encoding="utf-8")
        applied = install_into_hermes._patch_gateway_background_process_output_boundary(module, dry_run=False)
        text = module.read_text(encoding="utf-8")
        previous_hermes_home = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(base / "hermes-home")

        try:
            compile(text, str(module), "exec")
        except SyntaxError as exc:
            issues.append({"code": "patched_gateway_source_not_compilable", "error": str(exc)})

        namespace: dict[str, Any] = {}
        if not issues:
            exec(text, namespace)

        raw_output = "header-" + ("middle-line\n" * 500) + "tail"
        rendered = ""
        if namespace:
            rendered = namespace["_format_gateway_process_notification"](
                {
                    "type": "watch_match",
                    "session_id": "proc_very_large",
                    "command": "long command",
                    "pattern": "finished",
                    "output": raw_output,
                    "suppressed": 2,
                }
            )

        artifacts = sorted((base / "hermes-home" / "process_artifacts").glob("*.txt"))
        proof = {
            "host_patch_selected": install_into_hermes._host_patch_selected(
                "_patch_gateway_background_process_output_boundary",
                "core",
            ),
            "helpers_installed": "PROCESS_OUTPUT_CONTEXT_PREVIEW_CHARS = 600" in text,
            "watch_output_bounded": bool(rendered) and len(rendered) < 1300,
            "raw_middle_not_injected": bool(rendered) and rendered.count("middle-line") < 80,
            "artifact_written": len(artifacts) == 1,
            "artifact_preserves_full_output": bool(artifacts) and artifacts[0].read_text(encoding="utf-8") == raw_output,
            "agent_completion_path_patched": "_compact_gateway_process_output(session_id, \"agent_completion\"" in text,
            "user_completion_path_patched": "_compact_gateway_process_output(\n                        session_id,\n                        \"user_completion\"" in text,
            "running_update_path_patched": "_compact_gateway_process_output(\n                    session_id,\n                    \"running_update\"" in text,
            "old_raw_final_phrase_removed": "Here's the final output" not in text,
        }

        required = tuple(proof)
        missing = [key for key in required if proof.get(key) is not True]
        if missing:
            issues.append({"code": "context_pressure_proof_failed", "missing": missing})

        if previous_hermes_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = previous_hermes_home

        return {
            "schema": "brainstack.context_pressure_queue_liveness_proof.v1",
            "status": "pass" if not issues else "fail",
            "public_safe": True,
            "llm_calls_performed": False,
            "applied": applied,
            "rendered_length": len(rendered),
            "artifact_count": len(artifacts),
            "issues": issues,
            "proof": proof,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify context-pressure queue liveness output boundary.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_report()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
