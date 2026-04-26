from __future__ import annotations

import json
import subprocess
import sys

from scripts.brainstack_replay_canary import render_markdown, run_replay, scenarios


def test_replay_harness_passes_regression_gate() -> None:
    report = run_replay()

    assert report["schema"] == "brainstack.memory_replay_report.v1"
    assert report["summary"]["failed"] == 0
    assert report["summary"]["scenario_class_count"] == len(scenarios())
    assert report["summary"]["passed"] == len(scenarios()) * 4
    assert report["summary"]["modes"] == ["seeded_store", "full_lifecycle"]
    assert report["summary"]["fixture_variants"] == ["clean", "dirty"]
    assert report["summary"]["hook_coverage_verdicts"] == ["full", "synthetic"]
    assert {result["boundary_verdict"] for result in report["results"]} >= {
        "brainstack_selection",
        "packet_contract",
        "contaminated_memory_data",
        "basic_memory_truth",
        "donor_layer_l1",
        "donor_layer_l2",
        "donor_layer_l3",
        "cross_layer",
    }
    assert all(result["trace_fixture"]["latency_bucket"] == "ok" for result in report["results"])
    assert all("selected_counts" in result["trace_fixture"] for result in report["results"])
    assert all(result["first_broken_stage"] == "none" for result in report["results"])
    assert all("memory_answerability" in result for result in report["results"])
    assert all("hook_coverage" in result for result in report["results"])
    assert all("checkpoints" in result for result in report["results"])
    assert all("transaction_chain" in result for result in report["results"])
    assert all(result["checkpoints"]["post_session_equal_or_safer"] for result in report["results"])
    assert {
        (result["mode"], result["fixture_variant"]) for result in report["results"]
    } >= {
        ("seeded_store", "clean"),
        ("seeded_store", "dirty"),
        ("full_lifecycle", "clean"),
        ("full_lifecycle", "dirty"),
    }
    assert {
        "BMT-LITERAL",
        "BMT-PRIOR-EVENT",
        "BMT-ASSIGNMENT",
        "BMT-SUPERSESSION",
        "BMT-NO-EVIDENCE",
        "BMT-PARAPHRASE",
        "G-SCOPE",
        "G-PACKET",
        "G-RECEIPT",
        "L1-HINDSIGHT-BANK",
        "L2-GRAPH-CONFLICT",
        "L2-GRAPH-ALIAS",
        "L3-MEMPALACE-LIFECYCLE",
        "L3-MEMPALACE-REDACTION",
        "L3-MEMPALACE-IDEMPOTENCE",
    } <= {result["contract_id"] for result in report["results"]}


def test_replay_harness_cli_writes_json_and_markdown(tmp_path) -> None:
    output_path = tmp_path / "replay.json"
    markdown_path = tmp_path / "replay.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/brainstack_replay_canary.py",
            "--output",
            str(output_path),
            "--markdown",
            str(markdown_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_path.read_text())
    assert payload["summary"]["failed"] == 0
    assert "Brainstack Deterministic Memory Replay" in markdown_path.read_text()
    assert payload["summary"]["modes"] == ["seeded_store", "full_lifecycle"]
    assert payload["summary"]["fixture_variants"] == ["clean", "dirty"]


def test_replay_markdown_contains_boundary_and_trace() -> None:
    markdown = render_markdown(run_replay(["assistant_authored_assignment_residue"]))

    assert "boundary_verdict" in markdown
    assert "selected_counts" in markdown
    assert "assistant_authored_current_assignment_residue" in markdown
    assert "memory_answerability" in markdown
    assert "hook_coverage" in markdown
    assert "fixture_variant" in markdown
    assert "first_broken_stage" in markdown
