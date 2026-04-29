from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "measure_packet_budget_shadow_rollout.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("measure_packet_budget_shadow_rollout", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shadow_rollout_report_is_measurement_only() -> None:
    module = _load_module()

    report = module.build_report(
        root=ROOT,
        fixture_dir=ROOT / "tests/fixtures/public_memory_kernel",
        max_candidate_tokens=120,
        include_public_fixtures=True,
    )
    runtime = report["runtime_shadow"]
    metrics = report["required_metrics"]

    assert report["measurement_only"] is True
    assert report["production_optimization_enabled"] is False
    assert report["production_savings_claim"] is False
    assert report["activation_decision"]["active_default_justified"] is False
    assert report["shadow_output_changed"] is False
    assert metrics["scenario_count"] >= 12
    assert metrics["baseline_candidate_tokens"] > metrics["shadow_budget_candidate_tokens"]
    assert metrics["estimated_delta_tokens"] > 0
    assert metrics["production_savings_claim"] is False
    assert runtime["scenario_count"] >= 4
    assert runtime["baseline_candidate_tokens"] > runtime["shadow_budget_candidate_tokens"]
    assert runtime["estimated_delta_tokens"] > 0
    assert runtime["protected_truth_drop_attempts"] == 0
    assert runtime["output_changed_in_shadow"] is False
    assert report["public_fixture_measurement"]["fixture_status"] == "pass"


def test_shadow_rollout_fail_closed_stays_visible() -> None:
    module = _load_module()

    runtime = module.measure_runtime_shadow(max_candidate_tokens=1)

    assert runtime["fail_closed_count"] >= 1
    assert runtime["output_changed_in_shadow"] is False
    assert runtime["production_savings_claim"] is False
