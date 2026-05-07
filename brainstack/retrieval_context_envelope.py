from __future__ import annotations

import hashlib
from typing import Any, Mapping


RETRIEVAL_CONTEXT_ENVELOPE_SCHEMA = "brainstack.retrieval_context_envelope.v1"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _list_text(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _short_hash(value: str) -> str:
    text = _text(value)
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _fact_class(row: Mapping[str, Any]) -> str:
    value = _text(row.get("fact_class"))
    if value:
        return value
    row_type = _text(row.get("row_type"))
    if row_type == "conflict":
        return "conflict"
    if row_type == "state":
        return "explicit_state_current" if bool(row.get("is_current")) else "explicit_state_prior"
    if row_type == "relation":
        return "explicit_relation"
    return row_type


def _count_graph_stale_prior_conflict(graph_rows: list[Mapping[str, Any]]) -> int:
    return sum(1 for row in graph_rows if _fact_class(row) in {"conflict", "explicit_state_prior", "explicit_state_expired"})


def _source_sync_counts(corpus_rows: list[Mapping[str, Any]]) -> dict[str, int]:
    selected = 0
    expand_handles = 0
    for row in corpus_rows:
        metadata = _mapping(row.get("metadata"))
        source_sync = _mapping(metadata.get("source_sync_spine"))
        if not source_sync:
            document_metadata = _mapping(row.get("document_metadata"))
            source_sync = _mapping(document_metadata.get("source_sync_spine"))
        if not source_sync:
            continue
        selected += 1
        bounded = _mapping(source_sync.get("bounded_expand"))
        if bool(bounded.get("available")) and _text(source_sync.get("source_handle")):
            expand_handles += 1
    return {"selected": selected, "expand_handles": expand_handles}


def _behavior_card_summary(system_substrate: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    delivery = _mapping(system_substrate.get("active_preference_delivery_inspect"))
    contract = _mapping(system_substrate.get("active_preference_contract"))
    if not delivery:
        snapshot = _mapping(policy.get("behavior_policy_snapshot"))
        contract = _mapping(snapshot.get("active_preference_contract"))
    rule_count = int(delivery.get("active_rule_count") or delivery.get("compiled_rule_count") or 0)
    content_hash = _text(contract.get("content_hash") or contract.get("source_contract_hash"))
    return {
        "present": bool(rule_count or content_hash),
        "rule_count": rule_count,
        "hash": content_hash[:16],
    }


def build_retrieval_context_envelope(
    *,
    principal_scope_key: str,
    adaptive_route_plan: Mapping[str, Any],
    current_truth_view: Mapping[str, Any],
    policy: Mapping[str, Any],
    packet_budget: Mapping[str, Any],
    profile_items: list[Mapping[str, Any]],
    task_rows: list[Mapping[str, Any]],
    operating_rows: list[Mapping[str, Any]],
    matched: list[Mapping[str, Any]],
    recent: list[Mapping[str, Any]],
    transcript_rows: list[Mapping[str, Any]],
    graph_rows: list[Mapping[str, Any]],
    corpus_rows: list[Mapping[str, Any]],
    system_substrate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    route_class = _text(adaptive_route_plan.get("route_class")) or "unknown"
    semantic = _mapping(adaptive_route_plan.get("semantic_retrieval"))
    control_plan = _mapping(policy.get("retrieval_control_plan"))
    plan_id = _text(adaptive_route_plan.get("plan_id")) or _text(control_plan.get("plan_id"))
    current_rebuild = _mapping(current_truth_view.get("rebuild"))
    current_counters = _mapping(current_truth_view.get("counters"))
    source_sync = _source_sync_counts(corpus_rows)
    support_only_count = (
        int(current_counters.get("support_only_count") or 0)
        + len(matched)
        + len(recent)
        + len(transcript_rows)
        + len(corpus_rows)
    )
    stale_prior_conflict_count = (
        int(current_truth_view.get("non_answerable_row_count") or 0)
        + _count_graph_stale_prior_conflict(graph_rows)
    )
    fresh_retrieval_ran = any(
        (
            profile_items,
            task_rows,
            operating_rows,
            matched,
            recent,
            transcript_rows,
            graph_rows,
            corpus_rows,
            int(current_truth_view.get("current_truth_row_count") or 0) > 0,
        )
    )
    scope_present = bool(_text(principal_scope_key))
    behavior_card = _behavior_card_summary(_mapping(system_substrate), policy)
    return {
        "schema": RETRIEVAL_CONTEXT_ENVELOPE_SCHEMA,
        "plan_id": plan_id,
        "route_class": route_class,
        "active_scope": {
            "kind": "principal_scoped" if scope_present else "global",
            "scope_hash": _short_hash(principal_scope_key) if scope_present else "",
            "raw_scope_in_envelope": False,
        },
        "allowed_shelves": _list_text(adaptive_route_plan.get("activated_shelves")),
        "skipped_shelves": _list_text(adaptive_route_plan.get("skipped_shelves")),
        "freshness": {
            "expectation": _text(current_rebuild.get("freshness_status")) or "route_gated",
            "fresh_retrieval_ran": bool(fresh_retrieval_ran),
            "current_truth_source": _text(current_rebuild.get("source")),
            "ordinary_hot_path_rebuild": bool(current_rebuild.get("ordinary_hot_path_rebuild")),
        },
        "semantic_retrieval": {
            "enabled": bool(semantic.get("enabled")),
            "reason": _text(semantic.get("reason")),
            "limit": int(semantic.get("limit") or control_plan.get("semantic_limit") or 0),
            "allowed_shelves": _list_text(semantic.get("allowed_shelves")),
        },
        "evidence_counts": {
            "current_truth": int(current_truth_view.get("current_truth_row_count") or 0),
            "support_only": support_only_count,
            "stale_prior_conflict": stale_prior_conflict_count,
            "profile": len(profile_items),
            "task": len(task_rows),
            "operating": len(operating_rows),
            "graph": len(graph_rows),
            "corpus": len(corpus_rows),
        },
        "source_sync": source_sync,
        "packet_budget": {
            "mode": _text(packet_budget.get("mode")),
            "status": _text(packet_budget.get("status")),
            "applied_to_output": bool(packet_budget.get("applied_to_output")),
            "fail_closed": bool(packet_budget.get("fail_closed")),
        },
        "behavior_card": behavior_card,
        "stale_retrieval_marker": {
            "present": bool(stale_prior_conflict_count or support_only_count),
            "redaction_scope": "metadata_only",
            "reason_code": "RETRIEVAL_CONTEXT_SUPPORT_OR_STALE_PRESENT"
            if stale_prior_conflict_count or support_only_count
            else "RETRIEVAL_CONTEXT_CURRENT_ONLY",
        },
        "public_safe": True,
        "raw_private_payload_in_envelope": False,
        "authority": "metadata_only_not_truth_writer",
    }


def render_retrieval_context_envelope_section(envelope: Mapping[str, Any] | None) -> str:
    if not isinstance(envelope, Mapping):
        return ""
    route = _text(envelope.get("route_class")) or "unknown"
    scope = _text(_mapping(envelope.get("active_scope")).get("kind")) or "unknown"
    freshness = _mapping(envelope.get("freshness"))
    counts = _mapping(envelope.get("evidence_counts"))
    semantic = _mapping(envelope.get("semantic_retrieval"))
    source_sync = _mapping(envelope.get("source_sync"))
    behavior = _mapping(envelope.get("behavior_card"))
    lines = [
        (
            f"- route={route}; scope={scope}; freshness={_text(freshness.get('expectation')) or 'unknown'}; "
            f"fresh_retrieval={str(bool(freshness.get('fresh_retrieval_ran'))).lower()}; "
            f"semantic={'enabled' if semantic.get('enabled') else 'skipped'}"
        ),
        (
            f"- evidence current_truth={int(counts.get('current_truth') or 0)}; "
            f"support_only={int(counts.get('support_only') or 0)}; "
            f"stale_prior_conflict={int(counts.get('stale_prior_conflict') or 0)}; "
            f"source_expand_handles={int(source_sync.get('expand_handles') or 0)}"
        ),
    ]
    if bool(behavior.get("present")):
        lines.append(
            f"- behavior_card rules={int(behavior.get('rule_count') or 0)}; hash={_text(behavior.get('hash')) or 'none'}"
        )
    return "## Brainstack Retrieval Context\n" + "\n".join(lines)
