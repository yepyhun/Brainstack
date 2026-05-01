from __future__ import annotations

from pathlib import Path

from scripts.check_phase249_ralph_gate import BLOCKED_SENTINEL, run_check


def test_phase249_ralph_gate_blocks_missing_plan(tmp_path: Path) -> None:
    result = run_check(tmp_path / "missing.md")

    assert result["status"] == "fail"
    assert result["issues"] == [
        {"code": "implementation_plan_missing", "path": str(tmp_path / "missing.md")}
    ]


def test_phase249_ralph_gate_blocks_open_items(tmp_path: Path) -> None:
    plan = tmp_path / "IMPLEMENTATION_PLAN.md"
    plan.write_text("# Plan\n\n## Open\n\n- fix real blocker\n\n## Done\n\n- old work\n", encoding="utf-8")

    result = run_check(plan)

    assert result["status"] == "fail"
    assert result["issues"] == [{"code": "implementation_plan_open_items", "count": 1}]
    assert result["open_items"] == ["fix real blocker"]


def test_phase249_ralph_gate_passes_no_open_items(tmp_path: Path) -> None:
    plan = tmp_path / "IMPLEMENTATION_PLAN.md"
    plan.write_text("# Plan\n\n## Open\n\n## Done\n\n- all work\n", encoding="utf-8")

    result = run_check(plan)

    assert result["status"] == "pass"
    assert result["issue_count"] == 0


def test_phase249_ralph_gate_allows_blocked_sentinel_without_fake_open_work(tmp_path: Path) -> None:
    plan = tmp_path / "IMPLEMENTATION_PLAN.md"
    plan.write_text(f"# Plan\n\n## Open\n\n- {BLOCKED_SENTINEL}\n", encoding="utf-8")

    result = run_check(plan)

    assert result["status"] == "pass"
    assert result["open_items"] == []
