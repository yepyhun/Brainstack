import json
import subprocess
import sys

from brainstack.outcome_harness import METRIC_NAMES, MODES, build_report


def _result(report, case_id, mode):
    for case in report["cases"]:
        if case["id"] == case_id:
            return case["results"][mode]
    raise AssertionError(f"missing case {case_id}")


def test_report_is_public_safe_read_only_and_complete():
    report = build_report()

    assert report["schema"] == "brainstack.memory_outcome_harness_report.v1"
    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["read_only"] is True
    assert report["side_effect_free"] is True
    assert report["harness_count"] >= 5
    assert report["mode_count"] == len(MODES)

    for case in report["cases"]:
        assert set(case["results"]) == set(MODES)
        for mode in MODES:
            assert set(case["results"][mode]["metrics"]) == set(METRIC_NAMES)


def test_current_truth_rejects_stale_authority():
    report = build_report()

    brainstack = _result(report, "current_truth_supersession", "brainstack_packet")
    raw_history = _result(report, "current_truth_supersession", "raw_history")

    assert brainstack["metrics"]["answer_correct"] is True
    assert brainstack["metrics"]["stale_or_forbidden_selected_count"] == 0
    assert brainstack["metrics"]["correction_needed"] is False
    assert raw_history["metrics"]["stale_or_forbidden_selected_count"] >= 1


def test_multi_profile_scope_isolation_has_no_brainstack_bleed():
    report = build_report()

    brainstack = _result(report, "multi_profile_isolation", "brainstack_packet")
    raw_history = _result(report, "multi_profile_isolation", "raw_history")

    assert brainstack["metrics"]["answer_correct"] is True
    assert brainstack["metrics"]["scope_bleed_count"] == 0
    assert raw_history["metrics"]["scope_bleed_count"] >= 1


def test_token_savings_and_honest_raw_history_baseline():
    report = build_report()

    assert report["proof"]["raw_history_baseline_represented"] is True
    assert report["summary"]["raw_history_answer_correct_count"] >= 3
    assert report["summary"]["brainstack_token_savings_cases"] >= 4

    for case in report["cases"]:
        result = case["results"]["brainstack_packet"]
        assert result["metrics"]["model_facing_memory_tokens"] <= result["metrics"]["raw_history_tokens"]


def test_report_does_not_leak_private_runtime_markers():
    report_text = json.dumps(build_report(), sort_keys=True)

    forbidden = [
        "/private/runtime/path",
        "private_user_handle",
        "private_agent_name",
        "private_project_code",
        "private_chat_platform",
        "private_container_name",
    ]
    for marker in forbidden:
        assert marker not in report_text


def test_cli_writes_report(tmp_path):
    out = tmp_path / "memory-outcome.json"

    completed = subprocess.run(
        [sys.executable, "scripts/run_memory_outcome_harness.py", "--out", str(out)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["status"] == "pass"
    assert "brainstack.memory_outcome_harness_report.v1" in completed.stdout
