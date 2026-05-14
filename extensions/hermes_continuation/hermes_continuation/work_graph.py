"""Continuation Work Graph validation.

The Work Graph is a read-only continuation map over external work-state refs.
It does not create, dispatch, mutate, or complete Kanban tasks.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


WORK_GRAPH_CONTRACT_SCHEMA = "hermes_continuation.work_graph_contract.v1"

TERMINAL_STATES = {"done", "completed"}
RUNNABLE_STATES = {"ready", "todo"}
BLOCKED_STATES = {"blocked", "failed", "crashed", "timed_out", "timeout"}
ALLOWED_FANIN_DECISIONS = {
    "next_frontier_created",
    "human_gate",
    "intentional_stop",
    "recovery_needed",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _items(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _refs(value: Any) -> list[str]:
    if not isinstance(value, list | tuple | set):
        return []
    return sorted({str(item).strip() for item in value if str(item).strip()})


def _node_id(node: Mapping[str, Any]) -> str:
    return _text(node.get("node_id") or node.get("id"))


def _node_status(node: Mapping[str, Any]) -> str:
    return _text(node.get("status") or node.get("state")).lower()


def _node_artifacts(node: Mapping[str, Any]) -> list[str]:
    return _refs(node.get("artifact_refs") or node.get("artifacts"))


def _has_explicit_terminal_reason(graph: Mapping[str, Any]) -> bool:
    state = _text(graph.get("state")).lower()
    return state in {"gated", "stopped", "stopped_intentionally", "recovery_needed"} or bool(
        _text(graph.get("terminal_reason") or graph.get("fanout_terminal_reason"))
    )


def validate_work_graph(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a compact continuation Work Graph without side effects."""

    nodes = _items(graph.get("nodes"))
    edges = _items(graph.get("edges"))
    nodes_by_id = {_node_id(node): node for node in nodes if _node_id(node)}
    fan_in_nodes = set(_refs(graph.get("fan_in_nodes")))
    fan_in_nodes.update(
        _node_id(node)
        for node in nodes
        if _text(node.get("node_type") or node.get("type")) in {"fan_in", "fanin"}
    )
    fanout_edges = [edge for edge in edges if _text(edge.get("edge_type")) == "fanout"]
    fanin_edges = [edge for edge in edges if _text(edge.get("edge_type")) == "fanin"]
    repair_edges = [edge for edge in edges if _text(edge.get("edge_type")) == "repair"]
    reason_codes: list[str] = []
    actionable_frontier_count = 0
    private_payload_present = _bool(graph.get("private_payload_present"))

    if private_payload_present:
        reason_codes.append("PRIVATE_PAYLOAD_PRESENT")

    if fanout_edges and not fan_in_nodes and not _has_explicit_terminal_reason(graph):
        reason_codes.append("FANOUT_WITHOUT_FANIN")

    for edge in edges:
        from_node = _text(edge.get("from_node"))
        to_node = _text(edge.get("to_node"))
        if from_node and from_node not in nodes_by_id:
            reason_codes.append("EDGE_FROM_NODE_MISSING")
        if to_node and to_node not in nodes_by_id:
            reason_codes.append("EDGE_TO_NODE_MISSING")
        if _text(edge.get("edge_type")) in {"fanout", "fanin", "repair"} and not _text(edge.get("idempotency_key")):
            reason_codes.append("EDGE_IDEMPOTENCY_KEY_MISSING")

    for node in nodes:
        status = _node_status(node)
        node_id = _node_id(node)
        blocked_by = _refs(node.get("blocked_by"))
        if status in TERMINAL_STATES and not _node_artifacts(node) and node_id not in fan_in_nodes:
            reason_codes.append("DONE_NODE_MISSING_ARTIFACT")
        if status in RUNNABLE_STATES:
            if blocked_by:
                reason_codes.append("PARENT_BLOCKED_TODO_NOT_ACTIONABLE")
            else:
                actionable_frontier_count += 1

    for fanin_id in fan_in_nodes:
        node = nodes_by_id.get(fanin_id)
        if node is None:
            reason_codes.append("FANIN_NODE_MISSING")
            continue
        decision = _text(node.get("decision") or node.get("fan_in_decision"))
        status = _node_status(node)
        if status in TERMINAL_STATES and decision not in ALLOWED_FANIN_DECISIONS:
            reason_codes.append("FANIN_MISSING_ALLOWED_DECISION")
        required_parent_nodes = _refs(node.get("required_parent_nodes") or node.get("parents"))
        if not required_parent_nodes:
            required_parent_nodes = sorted(
                _text(edge.get("from_node")) for edge in fanin_edges if _text(edge.get("to_node")) == fanin_id
            )
        for parent_id in required_parent_nodes:
            parent = nodes_by_id.get(parent_id)
            if parent is None:
                reason_codes.append("FANIN_PARENT_MISSING")
                continue
            parent_status = _node_status(parent)
            if parent_status in TERMINAL_STATES and not _node_artifacts(parent):
                reason_codes.append("FANIN_PARENT_PROOF_MISSING")
            if parent_status in BLOCKED_STATES:
                has_repair = any(
                    _text(edge.get("from_node")) == parent_id and _text(edge.get("edge_type")) == "repair"
                    for edge in repair_edges
                ) or any(_text(candidate.get("repair_of")) == parent_id for candidate in nodes)
                if not has_repair and decision != "recovery_needed":
                    reason_codes.append("BLOCKED_PARENT_WITHOUT_REPAIR")

    if _bool(graph.get("work_graph_mutates_kanban")):
        reason_codes.append("WORK_GRAPH_MUTATES_KANBAN")

    critical_reasons = {
        "PRIVATE_PAYLOAD_PRESENT",
        "FANOUT_WITHOUT_FANIN",
        "FANIN_MISSING_ALLOWED_DECISION",
        "DONE_NODE_MISSING_ARTIFACT",
        "FANIN_PARENT_PROOF_MISSING",
        "FANIN_NODE_MISSING",
        "FANIN_PARENT_MISSING",
        "WORK_GRAPH_MUTATES_KANBAN",
    }
    if any(reason in critical_reasons for reason in reason_codes):
        verdict = "critical"
    elif reason_codes:
        verdict = "degraded"
    else:
        verdict = "healthy"
        reason_codes.append("WORK_GRAPH_VALID")

    repair_targets = {
        _text(edge.get("from_node"))
        for edge in repair_edges
        if _text(edge.get("from_node"))
    }
    repair_targets.update(
        _text(node.get("repair_of"))
        for node in nodes
        if _text(node.get("repair_of"))
    )

    return {
        "schema": WORK_GRAPH_CONTRACT_SCHEMA,
        "read_only": True,
        "side_effect_free": True,
        "public_safe": not private_payload_present,
        "verdict": verdict,
        "graph_id": _text(graph.get("graph_id")) or "unknown",
        "generation": int(graph.get("generation") or 0),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "fan_in_count": len(fan_in_nodes),
        "fanout_edge_count": len(fanout_edges),
        "repair_branch_count": len(repair_targets),
        "actionable_frontier_count": actionable_frontier_count,
        "reason_codes": sorted(set(reason_codes)),
        "agent_claim": f"work_graph_{verdict}",
    }


__all__ = [
    "ALLOWED_FANIN_DECISIONS",
    "WORK_GRAPH_CONTRACT_SCHEMA",
    "validate_work_graph",
]
