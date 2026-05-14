from __future__ import annotations

from hermes_continuation.work_graph import validate_work_graph


def test_fanout_without_fanin_or_terminal_reason_fails() -> None:
    graph = {
        "graph_id": "g1",
        "nodes": [
            {"node_id": "root", "status": "done", "postcondition": "split"},
            {"node_id": "a", "status": "ready", "postcondition": "artifact"},
        ],
        "edges": [{"from_node": "root", "to_node": "a", "edge_type": "fanout"}],
    }

    verdict = validate_work_graph(graph)

    assert verdict["verdict"] == "critical"
    assert "FANOUT_WITHOUT_FANIN" in verdict["reason_codes"]


def test_fanin_without_allowed_decision_fails() -> None:
    graph = {
        "graph_id": "g2",
        "nodes": [
            {"node_id": "a", "status": "done", "artifact_refs": ["artifact:a"], "postcondition": "done"},
            {"node_id": "join", "status": "done", "node_type": "fan_in", "required_parent_nodes": ["a"]},
        ],
        "edges": [{"from_node": "a", "to_node": "join", "edge_type": "fanin"}],
        "fan_in_nodes": ["join"],
    }

    verdict = validate_work_graph(graph)

    assert verdict["verdict"] == "critical"
    assert "FANIN_MISSING_ALLOWED_DECISION" in verdict["reason_codes"]


def test_child_done_without_artifact_fails_postcondition() -> None:
    graph = {
        "graph_id": "g3",
        "nodes": [
            {"node_id": "a", "status": "done", "postcondition": "artifact_required"},
            {
                "node_id": "join",
                "status": "done",
                "node_type": "fan_in",
                "required_parent_nodes": ["a"],
                "decision": "recovery_needed",
            },
        ],
        "edges": [{"from_node": "a", "to_node": "join", "edge_type": "fanin"}],
        "fan_in_nodes": ["join"],
    }

    verdict = validate_work_graph(graph)

    assert verdict["verdict"] == "critical"
    assert "DONE_NODE_MISSING_ARTIFACT" in verdict["reason_codes"]


def test_parent_blocked_todo_does_not_count_as_actionable_frontier() -> None:
    graph = {
        "graph_id": "g4",
        "nodes": [
            {"node_id": "parent", "status": "blocked", "postcondition": "blocked"},
            {
                "node_id": "child",
                "status": "todo",
                "blocked_by": ["parent"],
                "postcondition": "artifact",
            },
        ],
    }

    verdict = validate_work_graph(graph)

    assert verdict["actionable_frontier_count"] == 0
    assert "PARENT_BLOCKED_TODO_NOT_ACTIONABLE" in verdict["reason_codes"]


def test_valid_split_fanin_graph_passes_with_repair_edge() -> None:
    graph = {
        "graph_id": "g5",
        "generation": 2,
        "nodes": [
            {"node_id": "root", "status": "done", "artifact_refs": ["artifact:root"], "postcondition": "split"},
            {"node_id": "a", "status": "done", "artifact_refs": ["artifact:a"], "postcondition": "artifact"},
            {"node_id": "b", "status": "blocked", "postcondition": "needs_repair"},
            {
                "node_id": "repair-b",
                "status": "ready",
                "repair_of": "b",
                "postcondition": "repair_artifact",
            },
            {
                "node_id": "join",
                "status": "done",
                "node_type": "fan_in",
                "required_parent_nodes": ["a", "b"],
                "decision": "recovery_needed",
                "postcondition": "fan_in_decision",
            },
        ],
        "edges": [
            {"from_node": "root", "to_node": "a", "edge_type": "fanout", "idempotency_key": "g5:2:a"},
            {"from_node": "root", "to_node": "b", "edge_type": "fanout", "idempotency_key": "g5:2:b"},
            {"from_node": "a", "to_node": "join", "edge_type": "fanin", "idempotency_key": "g5:2:join:a"},
            {"from_node": "b", "to_node": "join", "edge_type": "fanin", "idempotency_key": "g5:2:join:b"},
            {"from_node": "b", "to_node": "repair-b", "edge_type": "repair", "idempotency_key": "g5:2:repair:b"},
        ],
        "fan_in_nodes": ["join"],
    }

    verdict = validate_work_graph(graph)

    assert verdict["verdict"] == "healthy"
    assert verdict["actionable_frontier_count"] == 1
    assert verdict["repair_branch_count"] == 1

