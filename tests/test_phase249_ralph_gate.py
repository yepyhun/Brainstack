from __future__ import annotations

from pathlib import Path

from scripts.check_phase249_ralph_gate import run_check


def test_phase249_ralph_gate_blocks_missing_plan(tmp_path: Path) -> None:
    result = run_check(tmp_path / "missing.md")

    assert result["status"] == "fail"
    assert result["issues"] == [
        {"code": "implementation_plan_missing", "path": str(tmp_path / "missing.md")}
    ]
    assert result["done_allowed"] is False
    assert result["stop_allowed"] is False
    assert result["loop_enforcement"]["must_continue"] is True  # type: ignore[index]
    assert result["next_action"]["action"] == "continue_loop"  # type: ignore[index]


def test_phase249_ralph_gate_blocks_open_items(tmp_path: Path) -> None:
    plan = tmp_path / "IMPLEMENTATION_PLAN.md"
    plan.write_text("# Plan\n\n## Open\n\n- fix real blocker\n\n## Done\n\n- old work\n", encoding="utf-8")

    result = run_check(plan)

    assert result["status"] == "fail"
    assert result["issues"] == [{"code": "implementation_plan_open_items", "count": 1}]
    assert result["open_items"] == ["fix real blocker"]
    assert result["done_allowed"] is False
    assert result["stop_allowed"] is False
    assert result["loop_enforcement"]["must_continue"] is True  # type: ignore[index]
    assert result["next_action"]["action"] == "continue_loop"  # type: ignore[index]
    assert result["next_action"]["work_item"] == "fix real blocker"  # type: ignore[index]


def test_phase249_ralph_gate_passes_no_open_items(tmp_path: Path) -> None:
    plan = tmp_path / "IMPLEMENTATION_PLAN.md"
    plan.write_text("# Plan\n\n## Open\n\n## Done\n\n- all work\n", encoding="utf-8")

    result = run_check(plan)

    assert result["status"] == "pass"
    assert result["issue_count"] == 0
    assert result["done_allowed"] is True
    assert result["stop_allowed"] is True
    assert result["loop_enforcement"]["must_continue"] is False  # type: ignore[index]


def test_phase249_ralph_gate_blocks_blocked_sentinel_and_forces_loop(tmp_path: Path) -> None:
    plan = tmp_path / "IMPLEMENTATION_PLAN.md"
    sentinel = "BLOCKED: exact proof missing"
    plan.write_text(f"# Plan\n\n## Open\n\n- {sentinel}\n", encoding="utf-8")

    result = run_check(plan)

    assert result["status"] == "fail"
    assert result["open_items"] == []
    assert result["blocked_items"] == [sentinel]
    assert result["done_allowed"] is False
    assert result["stop_allowed"] is False
    assert result["loop_enforcement"]["must_continue"] is True  # type: ignore[index]
    assert result["next_action"]["action"] == "continue_loop"  # type: ignore[index]
