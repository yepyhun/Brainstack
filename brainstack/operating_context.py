from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from .consolidation import consolidation_source_status
from .operating_truth import (
    OPERATING_RECORD_ACTIVE_WORK,
    OPERATING_RECORD_CANONICAL_POLICY,
    OPERATING_RECORD_COMPLETED_OUTCOME,
    OPERATING_RECORD_CURRENT_COMMITMENT,
    OPERATING_RECORD_DISCARDED_WORK,
    OPERATING_RECORD_EXTERNAL_OWNER_POINTER,
    OPERATING_RECORD_LIVE_SYSTEM_STATE,
    OPERATING_RECORD_NEXT_STEP,
    OPERATING_RECORD_OPEN_DECISION,
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
    OPERATING_RECORD_RUNTIME_APPROVAL_POLICY,
    is_background_operating_record,
    is_background_recent_work,
)
from .local_typed_understanding import build_session_recovery_contract


OPERATING_CONTEXT_SNAPSHOT_VERSION = 1
DEFAULT_OPERATING_CONTEXT_CHAR_BUDGET = 900

_STABLE_PROFILE_CATEGORIES = {"identity", "shared_work"}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _trim(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _unique_lines(values: Iterable[str], *, limit: int) -> List[str]:
    lines: List[str] = []
    seen: set[str] = set()
    for raw in values:
        text = _normalize_text(raw)
        if not text:
            continue
        lowered = text.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        lines.append(text)
        if len(lines) >= limit:
            break
    return lines


def _profile_item_supports_stable_signal(item: Mapping[str, Any]) -> bool:
    category = str(item.get("category") or "").strip()
    if category == "identity":
        return True
    if category != "shared_work":
        return False
    source = str(item.get("source") or "").strip().casefold()
    metadata = item.get("metadata")
    payload = metadata if isinstance(metadata, Mapping) else {}
    source_kind = str(payload.get("source_kind") or "").strip().casefold().replace("-", "_")
    if source.startswith("tier2:") or source.startswith("on_session_end:recent_work_consolidation"):
        return False
    if source_kind in {"tier2_idle_window", "tier2_batch", "session_consolidation", "background_evidence"}:
        return False
    return source.startswith("explicit") or source.startswith("host") or source_kind in {
        "explicit_operating_truth",
        "manual_migration",
    }


def _build_stable_profile_entries(profile_items: Iterable[Mapping[str, Any]], *, limit: int) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in profile_items:
        category = str(item.get("category") or "").strip()
        if category not in _STABLE_PROFILE_CATEGORIES:
            continue
        if not _profile_item_supports_stable_signal(item):
            continue
        stable_key = str(item.get("stable_key") or "").strip()
        content = _normalize_text(item.get("content"))
        if not content:
            continue
        entry_key = (category, content.casefold())
        if entry_key in seen:
            continue
        seen.add(entry_key)
        entries.append(
            {
                "category": category,
                "stable_key": stable_key,
                "content": content,
            }
        )
        if len(entries) >= limit:
            break
    return entries


def _build_active_work_summary(continuity_rows: Iterable[Mapping[str, Any]]) -> str:
    for row in continuity_rows:
        if str(row.get("kind") or "").strip() != "tier2_summary":
            continue
        summary = _normalize_text(row.get("content"))
        if summary:
            return summary
    return ""


def _operating_record_lines(
    operating_rows: Iterable[Mapping[str, Any]],
    *,
    record_type: str,
    limit: int,
    include_background: bool = False,
) -> List[str]:
    return _unique_lines(
        (
            str(row.get("content") or "")
            for row in operating_rows
            if str(row.get("record_type") or "").strip() == record_type
            and (include_background or not is_background_operating_record(dict(row)))
        ),
        limit=limit,
    )


def _recent_work_line_and_status(
    operating_rows: Iterable[Mapping[str, Any]],
    *,
    continuity_rows: Iterable[Mapping[str, Any]],
) -> tuple[str, Dict[str, Any]]:
    continuity_list = [dict(row) for row in continuity_rows]
    for row in operating_rows:
        if str(row.get("record_type") or "").strip() != OPERATING_RECORD_RECENT_WORK_SUMMARY:
            continue
        if is_background_recent_work(dict(row)):
            continue
        status = consolidation_source_status(
            row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {},
            source_rows=continuity_list,
        )
        if status.get("status") == "stale_source_changed":
            return "", status
        content = _normalize_text(row.get("content"))
        if content:
            return content, status
    return "", {"status": "none", "source_kind": "", "source_count": 0}


def _build_open_decisions(continuity_rows: Iterable[Mapping[str, Any]], *, limit: int) -> List[str]:
    return _unique_lines(
        (
            str(row.get("content") or "")
            for row in continuity_rows
            if str(row.get("kind") or "").strip() == "decision"
        ),
        limit=limit,
    )


def _build_current_commitments(
    operating_rows: Iterable[Mapping[str, Any]],
    task_rows: Iterable[Mapping[str, Any]],
    *,
    limit: int,
) -> List[str]:
    records = _operating_record_lines(
        operating_rows,
        record_type=OPERATING_RECORD_CURRENT_COMMITMENT,
        limit=limit,
    )
    if records:
        return records
    return _unique_lines(
        (
            str(row.get("title") or "")
            for row in task_rows
            if str(row.get("item_type") or "").strip() == "commitment"
        ),
        limit=limit,
    )


def _build_external_owner_pointers(
    operating_rows: Iterable[Mapping[str, Any]],
    *,
    limit: int,
) -> List[Dict[str, str]]:
    lines = _operating_record_lines(
        operating_rows,
        record_type=OPERATING_RECORD_EXTERNAL_OWNER_POINTER,
        limit=limit,
    )
    return [{"content": line} for line in lines]


def _build_runtime_approval_policy(
    operating_rows: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    policy_rows = [
        dict(row)
        for row in operating_rows
        if str(row.get("record_type") or "").strip() == OPERATING_RECORD_RUNTIME_APPROVAL_POLICY
    ]
    if not policy_rows:
        return {"present": False, "domains": [], "content": "", "source": ""}
    policy_rows.sort(
        key=lambda row: (
            str(row.get("updated_at") or ""),
            str(row.get("created_at") or ""),
        ),
        reverse=True,
    )
    row = policy_rows[0]
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    domains = []
    for raw in (metadata or {}).get("domains") or ():
        if not isinstance(raw, Mapping):
            continue
        name = _normalize_text(raw.get("name") or raw.get("domain"))
        if not name:
            continue
        domains.append(
            {
                "name": name,
                "approval_required": bool(raw.get("approval_required")),
                "default_action": _normalize_text(raw.get("default_action") or raw.get("action")),
                "risk_class": _normalize_text(raw.get("risk_class")),
            }
        )
    return {
        "present": True,
        "content": _normalize_text(row.get("content")),
        "source": _normalize_text(row.get("source")),
        "domains": domains,
        "default_action": _normalize_text((metadata or {}).get("default_action")),
    }


def _build_runtime_handoff_tasks(
    task_rows: Iterable[Mapping[str, Any]],
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    for row in task_rows:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
        if not bool((metadata or {}).get("runtime_handoff")):
            continue
        tasks.append(
            {
                "stable_key": str(row.get("stable_key") or "").strip(),
                "title": _normalize_text(row.get("title")),
                "status": _normalize_text(row.get("status")),
                "due_date": _normalize_text(row.get("due_date")),
                "item_type": _normalize_text(row.get("item_type")),
                "domain": _normalize_text((metadata or {}).get("domain")),
                "action": _normalize_text((metadata or {}).get("action")),
                "risk_class": _normalize_text((metadata or {}).get("risk_class")),
                "approval_required": bool((metadata or {}).get("approval_required")),
                "task_id": _normalize_text((metadata or {}).get("task_id")) or _normalize_text(row.get("stable_key")),
            }
        )
        if len(tasks) >= limit:
            break
    return tasks


def _build_canonical_policy(
    operating_rows: Iterable[Mapping[str, Any]],
    *,
    limit: int,
) -> Dict[str, Any]:
    rules: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in operating_rows:
        if str(row.get("record_type") or "").strip() != OPERATING_RECORD_CANONICAL_POLICY:
            continue
        metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
        content = _normalize_text(row.get("content"))
        if not content:
            continue
        rule_id = _normalize_text((metadata or {}).get("rule_id")) or _normalize_text(row.get("stable_key"))
        if not rule_id or rule_id in seen:
            continue
        seen.add(rule_id)
        rules.append(
            {
                "rule_id": rule_id,
                "rule_class": _normalize_text((metadata or {}).get("rule_class")) or "explicit_rule",
                "content": content,
                "source": _normalize_text(row.get("source")),
                "source_authority": _normalize_text((metadata or {}).get("source_authority")) or "explicit",
                "updated_at": _normalize_text(row.get("updated_at")),
            }
        )
        if len(rules) >= limit:
            break
    return {
        "present": bool(rules),
        "rule_count": len(rules),
        "rules": rules,
        "runtime_read_only": True,
        "authority_owner": "brainstack.canonical_policy",
    }


def _build_session_state(lifecycle_state: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(lifecycle_state, Mapping):
        return {
            "present": False,
            "active": False,
            "frontier_turn_number": 0,
            "last_snapshot_kind": "",
            "last_snapshot_turn_number": 0,
            "last_finalized_turn_number": 0,
        }
    frontier_turn_number = max(0, int(lifecycle_state.get("current_frontier_turn_number") or 0))
    last_snapshot_turn_number = max(0, int(lifecycle_state.get("last_snapshot_turn_number") or 0))
    last_finalized_turn_number = max(0, int(lifecycle_state.get("last_finalized_turn_number") or 0))
    return {
        "present": True,
        "active": frontier_turn_number > last_finalized_turn_number,
        "frontier_turn_number": frontier_turn_number,
        "last_snapshot_kind": str(lifecycle_state.get("last_snapshot_kind") or "").strip(),
        "last_snapshot_turn_number": last_snapshot_turn_number,
        "last_finalized_turn_number": last_finalized_turn_number,
    }


def build_operating_context_snapshot(
    *,
    principal_scope_key: str,
    compiled_behavior_policy_record: Mapping[str, Any] | None,
    profile_items: Iterable[Mapping[str, Any]],
    operating_rows: Iterable[Mapping[str, Any]],
    task_rows: Iterable[Mapping[str, Any]],
    continuity_rows: Iterable[Mapping[str, Any]],
    lifecycle_state: Mapping[str, Any] | None,
    stable_profile_limit: int = 4,
    decision_limit: int = 4,
) -> Dict[str, Any]:
    continuity_list = [dict(row) for row in continuity_rows]
    operating_list = [dict(row) for row in operating_rows]
    stable_profile_entries = _build_stable_profile_entries(profile_items, limit=stable_profile_limit)
    active_work_candidates = _operating_record_lines(
        operating_list,
        record_type=OPERATING_RECORD_ACTIVE_WORK,
        limit=1,
    )
    active_work_summary = active_work_candidates[0] if active_work_candidates else ""
    recent_work_summary, recent_work_source_status = _recent_work_line_and_status(
        operating_list,
        continuity_rows=continuity_list,
    )
    if not recent_work_summary and recent_work_source_status.get("status") == "none":
        recent_work_source_status = {"status": "none", "source_kind": "", "source_count": 0}
    open_decisions = _operating_record_lines(
        operating_list,
        record_type=OPERATING_RECORD_OPEN_DECISION,
        limit=decision_limit,
    )
    live_system_state = _operating_record_lines(
        operating_list,
        record_type=OPERATING_RECORD_LIVE_SYSTEM_STATE,
        limit=6,
    )
    current_commitments = _build_current_commitments(operating_list, task_rows, limit=4)
    next_steps = _operating_record_lines(
        operating_list,
        record_type=OPERATING_RECORD_NEXT_STEP,
        limit=4,
    )
    runtime_approval_policy = _build_runtime_approval_policy(operating_list)
    canonical_policy = _build_canonical_policy(operating_list, limit=8)
    runtime_handoff_tasks = _build_runtime_handoff_tasks(task_rows, limit=8)
    session_state = _build_session_state(lifecycle_state)
    external_owner_pointers = _build_external_owner_pointers(operating_list, limit=4)
    completed_outcomes = _operating_record_lines(
        operating_list,
        record_type=OPERATING_RECORD_COMPLETED_OUTCOME,
        limit=4,
    )
    discarded_work = _operating_record_lines(
        operating_list,
        record_type=OPERATING_RECORD_DISCARDED_WORK,
        limit=4,
    )
    proactive_guidance = ""
    if (
        active_work_summary
        or recent_work_summary
        or open_decisions
        or current_commitments
        or next_steps
        or runtime_handoff_tasks
    ):
        proactive_guidance = (
            "If the user re-engages vaguely, resume the active work or open decisions below before falling back to generic small talk. "
            "Do not invent reminders or scheduling state that is not grounded in the committed records."
        )
    session_recovery_contract = build_session_recovery_contract(
        live_system_state_count=len(live_system_state),
        runtime_handoff_task_count=len(runtime_handoff_tasks),
        current_commitment_count=len(current_commitments),
        next_step_count=len(next_steps),
        open_decision_count=len(open_decisions),
        approval_policy_present=bool(runtime_approval_policy.get("present")),
    )

    return {
        "snapshot_version": OPERATING_CONTEXT_SNAPSHOT_VERSION,
        "principal_scope_key": str(principal_scope_key or "").strip(),
        "behavior_policy": {
            "active": bool(compiled_behavior_policy_record),
            "compiler_version": str((compiled_behavior_policy_record or {}).get("compiler_version") or "").strip(),
            "source_contract_hash": str((compiled_behavior_policy_record or {}).get("source_contract_hash") or "").strip(),
        },
        "stable_profile_entries": stable_profile_entries,
        "stable_profile_entry_count": len(stable_profile_entries),
        "active_work_summary": active_work_summary,
        "recent_work_summary": recent_work_summary,
        "recent_work_summary_source_status": recent_work_source_status,
        "open_decisions": open_decisions,
        "open_decision_count": len(open_decisions),
        "live_system_state": live_system_state,
        "live_system_state_count": len(live_system_state),
        "current_commitments": current_commitments,
        "current_commitment_count": len(current_commitments),
        "next_steps": next_steps,
        "next_step_count": len(next_steps),
        "runtime_approval_policy": runtime_approval_policy,
        "canonical_policy": canonical_policy,
        "runtime_handoff_tasks": runtime_handoff_tasks,
        "runtime_handoff_task_count": len(runtime_handoff_tasks),
        "session_recovery_contract": session_recovery_contract,
        "completed_outcomes": completed_outcomes,
        "completed_outcome_count": len(completed_outcomes),
        "discarded_work": discarded_work,
        "discarded_work_count": len(discarded_work),
        "session_state": session_state,
        "operating_truth_rows": operating_list,
        "operating_truth_row_count": len(operating_list),
        "external_owner_pointers": external_owner_pointers,
        "external_owner_pointer_count": len(external_owner_pointers),
        "proactive_guidance": proactive_guidance,
        "owner_boundary": (
            "Brainstack owns canonical durable policy truth, bounded task and commitment truth recorded in its structured task memory, "
            "and committed operating/live-state truth recorded in its operating substrate. Reminders, scheduling, approval enforcement, and broader execution authority stay with dedicated runtime owners."
        ),
    }


def _append_block(lines: List[str], block: List[str], *, char_budget: int) -> bool:
    candidate = "\n".join([*lines, *block]) if lines else "\n".join(block)
    if len(candidate) > char_budget:
        return False
    lines.extend(block)
    return True


def render_operating_context_section(
    snapshot: Mapping[str, Any] | None,
    *,
    title: str = "# Brainstack Operating Context",
    char_budget: int = DEFAULT_OPERATING_CONTEXT_CHAR_BUDGET,
) -> str:
    if not isinstance(snapshot, Mapping):
        return ""

    lines: List[str] = [title]
    active_work_summary = _normalize_text(snapshot.get("active_work_summary"))
    recent_work_summary = _normalize_text(snapshot.get("recent_work_summary"))
    open_decisions = _unique_lines(snapshot.get("open_decisions") or [], limit=4)
    live_system_state = _unique_lines(snapshot.get("live_system_state") or [], limit=6)
    current_commitments = _unique_lines(snapshot.get("current_commitments") or [], limit=4)
    next_steps = _unique_lines(snapshot.get("next_steps") or [], limit=4)
    raw_runtime_approval_policy = snapshot.get("runtime_approval_policy")
    runtime_approval_policy: Mapping[str, Any] = (
        raw_runtime_approval_policy if isinstance(raw_runtime_approval_policy, Mapping) else {}
    )
    raw_canonical_policy = snapshot.get("canonical_policy")
    canonical_policy: Mapping[str, Any] = raw_canonical_policy if isinstance(raw_canonical_policy, Mapping) else {}
    runtime_handoff_tasks = list(snapshot.get("runtime_handoff_tasks") or [])
    raw_session_recovery_contract = snapshot.get("session_recovery_contract")
    session_recovery_contract: Mapping[str, Any] = (
        raw_session_recovery_contract if isinstance(raw_session_recovery_contract, Mapping) else {}
    )
    completed_outcomes = _unique_lines(snapshot.get("completed_outcomes") or [], limit=4)
    discarded_work = _unique_lines(snapshot.get("discarded_work") or [], limit=4)
    stable_profile_entries = list(snapshot.get("stable_profile_entries") or [])
    raw_session_state = snapshot.get("session_state")
    session_state: Mapping[str, Any] = raw_session_state if isinstance(raw_session_state, Mapping) else {}
    proactive_guidance = _normalize_text(snapshot.get("proactive_guidance"))
    owner_boundary = _normalize_text(snapshot.get("owner_boundary"))
    external_owner_pointers = list(snapshot.get("external_owner_pointers") or [])

    content_added = False

    if active_work_summary:
        content_added = _append_block(
            lines,
            [
                "",
                "Current work:",
                f"- {_trim(active_work_summary, 220)}",
            ],
            char_budget=char_budget,
        ) or content_added

    if recent_work_summary and recent_work_summary != active_work_summary:
        content_added = _append_block(
            lines,
            [
                "",
                "Recent work checkpoint:",
                f"- {_trim(recent_work_summary, 220)}",
            ],
            char_budget=char_budget,
        ) or content_added

    if open_decisions:
        decision_lines = ["", "Open decisions:"]
        for decision in open_decisions:
            decision_lines.append(f"- {_trim(decision, 180)}")
        content_added = _append_block(lines, decision_lines, char_budget=char_budget) or content_added

    if current_commitments:
        commitment_lines = ["", "Current commitments:"]
        for commitment in current_commitments:
            commitment_lines.append(f"- {_trim(commitment, 180)}")
        content_added = _append_block(lines, commitment_lines, char_budget=char_budget) or content_added

    if next_steps:
        next_step_lines = ["", "Next steps:"]
        for next_step in next_steps:
            next_step_lines.append(f"- {_trim(next_step, 180)}")
        content_added = _append_block(lines, next_step_lines, char_budget=char_budget) or content_added

    if live_system_state:
        live_state_lines = ["", "Supporting live runtime state (not workstream truth):"]
        for item in live_system_state:
            live_state_lines.append(f"- {_trim(item, 180)}")
        live_state_lines.append(
            "- This section is only authoritative for runtime mechanisms such as scheduler/pulse health."
        )
        live_state_lines.append(
            "- Do not use this section to answer current user project status or the agent's assigned workstream."
        )
        content_added = _append_block(lines, live_state_lines, char_budget=char_budget) or content_added

    if bool(runtime_approval_policy.get("present")):
        policy_lines = ["", "Runtime approval policy:"]
        content = _normalize_text(runtime_approval_policy.get("content"))
        if content:
            policy_lines.append(f"- {_trim(content, 180)}")
        for entry in list(runtime_approval_policy.get("domains") or [])[:6]:
            if not isinstance(entry, Mapping):
                continue
            name = _normalize_text(entry.get("name"))
            if not name:
                continue
            action = _normalize_text(entry.get("default_action")) or (
                "ask_user" if bool(entry.get("approval_required")) else "auto_approved"
            )
            risk_class = _normalize_text(entry.get("risk_class"))
            detail = f"{name}: {action}"
            if risk_class:
                detail += f" ({risk_class})"
            policy_lines.append(f"- {_trim(detail, 180)}")
        content_added = _append_block(lines, policy_lines, char_budget=char_budget) or content_added

    if bool(canonical_policy.get("present")):
        canonical_lines = ["", "Canonical policy:"]
        for rule in list(canonical_policy.get("rules") or [])[:4]:
            if not isinstance(rule, Mapping):
                continue
            content = _normalize_text(rule.get("content"))
            if not content:
                continue
            rule_class = _normalize_text(rule.get("rule_class"))
            prefix = f"[{rule_class}] " if rule_class else ""
            canonical_lines.append(f"- {prefix}{_trim(content, 180)}")
        content_added = _append_block(lines, canonical_lines, char_budget=char_budget) or content_added

    if runtime_handoff_tasks:
        handoff_lines = ["", "Runtime handoff tasks:"]
        for task in runtime_handoff_tasks[:4]:
            if not isinstance(task, Mapping):
                continue
            title = _normalize_text(task.get("title"))
            if not title:
                continue
            suffix_bits = []
            domain = _normalize_text(task.get("domain"))
            action = _normalize_text(task.get("action"))
            if domain:
                suffix_bits.append(domain)
            if action:
                suffix_bits.append(action)
            if bool(task.get("approval_required")):
                suffix_bits.append("approval required")
            suffix = f" [{' | '.join(suffix_bits)}]" if suffix_bits else ""
            handoff_lines.append(f"- {_trim(title, 150)}{suffix}")
        content_added = _append_block(lines, handoff_lines, char_budget=char_budget) or content_added

    if completed_outcomes:
        outcome_lines = ["", "Completed outcomes:"]
        for outcome in completed_outcomes:
            outcome_lines.append(f"- {_trim(outcome, 180)}")
        content_added = _append_block(lines, outcome_lines, char_budget=char_budget) or content_added

    if discarded_work:
        discarded_lines = ["", "Discarded or superseded work:"]
        for item in discarded_work:
            discarded_lines.append(f"- {_trim(item, 180)}")
        content_added = _append_block(lines, discarded_lines, char_budget=char_budget) or content_added

    if stable_profile_entries:
        profile_lines = ["", "Stable project signals:"]
        for entry in stable_profile_entries[:4]:
            label = str(entry.get("category") or "profile").replace("_", " ")
            profile_lines.append(f"- [{label}] {_trim(entry.get('content'), 160)}")
        content_added = _append_block(lines, profile_lines, char_budget=char_budget) or content_added

    if bool(session_state.get("active")) and proactive_guidance:
        content_added = _append_block(
            lines,
            [
                "",
                "Proactive continuity rule:",
                f"- {_trim(proactive_guidance, 220)}",
            ],
            char_budget=char_budget,
        ) or content_added

    if external_owner_pointers:
        pointer_lines = ["", "External owner pointers:"]
        for pointer in external_owner_pointers[:4]:
            pointer_lines.append(f"- {_trim(pointer.get('content'), 180)}")
        content_added = _append_block(lines, pointer_lines, char_budget=char_budget) or content_added

    if session_recovery_contract:
        recovery_lines = ["", "Session recovery contract:"]
        ordered = list(session_recovery_contract.get("ordered_checks") or [])
        for item in ordered[:5]:
            if not isinstance(item, Mapping):
                continue
            surface = _normalize_text(item.get("surface")).replace("_", " ")
            purpose = _normalize_text(item.get("purpose"))
            if not surface:
                continue
            recovery_lines.append(f"- {surface}: {_trim(purpose or 'startup check', 120)}")
        content_added = _append_block(lines, recovery_lines, char_budget=char_budget) or content_added

    if content_added and owner_boundary:
        _append_block(
            lines,
            [
                "",
                "Owner boundary:",
                f"- {_trim(owner_boundary, 180)}",
            ],
            char_budget=char_budget,
        )

    if not content_added:
        return ""
    return "\n".join(lines).strip()
