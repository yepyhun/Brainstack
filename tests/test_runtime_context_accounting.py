from __future__ import annotations

import json
from pathlib import Path

from brainstack.compression_pressure import classify_compression_pressure
from brainstack.runtime_context_accounting import (
    build_context_accounting_report,
    parse_compression_accounting,
)


def test_context_accounting_counts_tool_history_without_raw_content(tmp_path: Path) -> None:
    session = tmp_path / "session.json"
    session.write_text(
        json.dumps(
            {
                "system_prompt": "system rules",
                "tools": [{"name": "read_file", "description": "read"}],
                "messages": [
                    {"role": "user", "content": "short ask"},
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "call_id": "call_1",
                                "function": {"name": "read_file", "arguments": "{}"},
                            }
                        ],
                    },
                    {"role": "tool", "tool_call_id": "call_1", "content": "x" * 1000},
                    {"role": "tool", "name": "read_file", "content": "x" * 1000},
                    {"role": "tool", "name": "skill_view", "content": "y" * 2000},
                    {"role": "tool", "name": "brainstack_recall", "content": "z" * 100},
                ]
            }
        ),
        encoding="utf-8",
    )

    report = build_context_accounting_report([session])

    assert report["schema"] == "brainstack.runtime_context_accounting.v1"
    assert report["roles"]["tool"]["chars"] == 4100
    assert report["roles"]["system"]["chars"] == len("system rules")
    assert report["roles"]["tool_schema"]["chars"] > 0
    categories = {item["category"]: item for item in report["tool_categories"]}
    assert categories["read_file"]["chars"] == 2000
    assert categories["skill_view"]["chars"] == 2000
    assert categories["brainstack"]["chars"] == 100
    assert report["privacy"]["raw_content_included"] is False


def test_compression_pressure_marks_timeout_without_success_critical() -> None:
    log = "\n".join(
        [
            "Preflight compression: ~250,244 tokens >= 217,600 threshold.",
            "Compression summary failed: Codex auxiliary Responses stream exceeded 120.0s total timeout.",
        ]
    )
    compression = parse_compression_accounting(log)
    report = {
        "totals": {"tokens_est": 10},
        "compression": compression.to_dict(),
    }

    verdict = classify_compression_pressure(report)

    assert compression.failure_lines == 1
    assert compression.success_lines == 0
    assert verdict.verdict == "critical"
    assert "COMPRESSION_FAILURE_WITHOUT_SUCCESS" in verdict.reason_codes
    assert verdict.fallback_required is True
