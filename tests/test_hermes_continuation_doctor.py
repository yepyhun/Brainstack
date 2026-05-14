from __future__ import annotations

from hermes_continuation.doctor import continuation_extension_doctor


def test_continuation_extension_doctor_checks_core_contracts() -> None:
    report = continuation_extension_doctor()

    assert report["status"] == "pass"
    assert report["issues"] == []
    assert report["read_only"] is True
    assert report["side_effect_free"] is True
    assert report["capability"]["verdict"] == "healthy"
    assert report["completion"]["is_material_progress"] is True
    assert report["work_graph"]["actionable_frontier_count"] == 1
    assert report["trace_replay"]["verdict"] == "healthy"
