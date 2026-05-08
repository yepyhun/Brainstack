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

from scripts import install_into_hermes  # noqa: E402


def _fixture() -> str:
    return '''
class AIAgent:
    def _emit_interim_assistant_message(self, assistant_msg):
        cb = getattr(self, "interim_assistant_callback", None)
        if cb is None or not isinstance(assistant_msg, dict):
            return
        content = assistant_msg.get("content")

    def _run_codex_stream(self, api_kwargs: dict, client=None, on_first_delta=None):
        max_stream_retries = 1
        has_tool_calls = False
        first_delta_fired = False
        for attempt in range(max_stream_retries + 1):
            with active_client.responses.stream(**api_kwargs) as stream:
                for event in stream:
                    event_type = getattr(event, "type", "")
                        if "output_text.delta" in event_type or event_type == "response.output_text.delta":
                            delta_text = getattr(event, "delta", "")
                            if delta_text:
                                self._codex_streamed_text_parts.append(delta_text)
                            if delta_text and not has_tool_calls:
                                if not first_delta_fired:
                                    first_delta_fired = True
                                    if on_first_delta:
                                        try:
                                            on_first_delta()
                                        except Exception:
                                            pass
                                self._fire_stream_delta(delta_text)
                        elif "function_call" in event_type:
                            has_tool_calls = True
                    final_response = stream.get_final_response()

    def _call_chat_completions(self):
            content_parts: list = []
            tool_calls_acc: dict = {}
                if delta and delta.content:
                    content_parts.append(delta.content)
                    if not tool_calls_acc:
                        _fire_first_delta()
                        self._fire_stream_delta(delta.content)
                        deltas_were_sent["yes"] = True
                    else:
                        # Tool calls suppress regular content streaming (avoids
                        # displaying chatty "I'll use the tool..." text alongside
                        # tool calls).  But reasoning tags embedded in suppressed
                        # content should still reach the display — otherwise the
                        # reasoning box only appears as a post-response fallback,
                        # rendering it confusingly after the already-streamed
                        # response.  Route suppressed content through the stream
                        # delta callback so its tag extraction can fire the
                        # reasoning display.  Non-reasoning text is harmlessly
                        # suppressed by the CLI's _stream_delta when the stream
                        # box is already closed (tool boundary flush).
                        if self.stream_delta_callback:
                            try:
                                self.stream_delta_callback(delta.content)
                                self._record_streamed_assistant_text(delta.content)
                            except Exception:
                                pass
                if delta and delta.tool_calls:
                pass
            # Build mock response matching non-streaming shape
'''


def build_report() -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="brainstack-preface-boundary-") as raw:
        module = Path(raw) / "run_agent.py"
        module.write_text(_fixture(), encoding="utf-8")
        actions = install_into_hermes._patch_run_agent_tool_call_interim_boundary(module, dry_run=False)
        text = module.read_text(encoding="utf-8")
    proof = {
        "interim_tool_call_content_suppressed": "if assistant_msg.get(\"tool_calls\"):" in text
        and "Tool-call turns are transcript/API state" in text,
        "codex_stream_buffers_preface": "tool_boundary_text_buffer.append(delta_text)" in text,
        "codex_stream_flushes_only_after_boundary": "_flush_tool_boundary_text_buffer()" in text
        and "final_response = stream.get_final_response()" in text,
        "chat_stream_buffers_preface": "tool_boundary_text_buffer.append(delta.content)" in text,
        "chat_stream_flushes_only_without_tool_calls": "if not tool_calls_acc and tool_boundary_text_buffer:" in text,
        "safe_progress_callbacks_not_disabled_by_config": "interim_assistant_messages: false" not in text,
    }
    for key, passed in proof.items():
        if passed is not True:
            issues.append({"code": key})
    required_actions = {
        "run_agent:tool_call_interim_user_facing_boundary",
        "run_agent:codex_stream_tool_boundary_buffer",
        "run_agent:codex_stream_buffer_preface",
        "run_agent:codex_stream_flush_safe_final",
        "run_agent:chat_stream_tool_boundary_buffer",
        "run_agent:chat_stream_buffer_preface",
        "run_agent:chat_stream_flush_safe_final",
    }
    missing_actions = sorted(required_actions.difference(actions))
    if missing_actions:
        issues.append({"code": "missing_patch_actions", "missing": missing_actions})
    return {
        "schema": "brainstack.tool_call_preface_boundary_proof.v1",
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "public_safe": True,
        "llm_calls_performed": False,
        "actions": actions,
        "proof": proof,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify tool-call preface boundary patch.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_report()
    text = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
