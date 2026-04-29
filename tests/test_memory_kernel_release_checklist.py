from __future__ import annotations

from scripts.run_memory_kernel_release_checklist import _git_hygiene_from_lists, _report, CheckResult


def test_git_hygiene_blocks_dirty_source() -> None:
    summary = _git_hygiene_from_lists([" M brainstack/core/example.py"], [])

    assert summary["git_dirty"] is True
    assert summary["dirty_entry_count"] == 1
    assert summary["private_live_untracked_visible"] is False


def test_git_hygiene_blocks_visible_private_live_files() -> None:
    summary = _git_hygiene_from_lists(
        ["?? scripts/run_live_discord_e2e.py"],
        ["scripts/run_live_discord_e2e.py"],
    )

    assert summary["untracked_private_files_count"] == 1
    assert summary["untracked_private_files_policy"] == "blocked_if_visible"
    assert summary["private_live_untracked_visible"] is True


def test_release_report_allows_dev_dirty_without_release_allowed() -> None:
    checks = [
        CheckResult("public_memory_kernel_corpus", "pass", ["ok"], 0, {}),
        CheckResult("git_hygiene", "fail", ["git"], 0, {"git_dirty": True}),
    ]

    report = _report(checks, ignore_git_dirty_for_dev=True)

    assert report["status"] == "pass"
    assert report["release_allowed"] is False
    assert report["failed_checks"] == ["git_hygiene"]


def test_release_report_fails_non_git_failure_even_in_dev_mode() -> None:
    checks = [
        CheckResult("public_memory_kernel_corpus", "fail", ["bad"], 1, {}),
        CheckResult("git_hygiene", "fail", ["git"], 0, {"git_dirty": True}),
    ]

    report = _report(checks, ignore_git_dirty_for_dev=True)

    assert report["status"] == "fail"
    assert report["release_allowed"] is False
    assert report["non_git_failures"] == ["public_memory_kernel_corpus"]
