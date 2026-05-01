from __future__ import annotations

from scripts.audit_tier2_structural_unbreakability import (
    DECISION_GATE,
    RECONCILER_WRITES,
    _decision_core_purity_issues,
    _ungated_write_issues,
    run_structural_audit,
)
from scripts.audit_tier2_unbreakable_operation import EXACT_DONE_GATE_CLAIM


def test_structural_audit_passes_current_tier2_write_boundaries() -> None:
    result = run_structural_audit(claim=EXACT_DONE_GATE_CLAIM)

    assert result["status"] == "pass"
    assert result["issue_count"] == 0
    assert result["proof_equivalence"]["status"] == "partial"
    assert result["proof_equivalence"]["machine_proof_same_as_claim"] is False
    assert result["proof_equivalence"]["proof_source"] == "structural_source_reachability_proof"
    assert result["proof_equivalence"]["structural_reachability_only"] is True


def test_structural_audit_detects_reconciler_write_before_gate() -> None:
    source = """
def _reconcile_relations():
    writer.write_graph_relation()
    evaluate_tier2_decision_core_gate()
"""

    issues = _ungated_write_issues(
        source=source,
        file_path="brainstack/reconciler.py",
        write_names=RECONCILER_WRITES,
        guard_names={DECISION_GATE},
        function_names={"_reconcile_relations"},
    )

    assert issues == [
        {
            "code": "durable_write_without_prior_gate",
            "file": "brainstack/reconciler.py",
            "function": "_reconcile_relations",
            "write_call": "write_graph_relation",
            "line": 3,
            "required_guard": [DECISION_GATE],
        }
    ]


def test_structural_audit_rejects_forbidden_decision_core_side_effects() -> None:
    source = """
from brainstack.db import BrainstackStore

def build_tier2_decision_plan(packet):
    store.write_graph_state()
"""

    issues = _decision_core_purity_issues(source, file_path="brainstack/tier2_decision_core.py")
    codes = {issue["code"] for issue in issues}

    assert "decision_core_forbidden_import" in codes
    assert "decision_core_forbidden_call" in codes
