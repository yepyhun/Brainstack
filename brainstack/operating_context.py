from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


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


def _build_stable_profile_entries(profile_items: Iterable[Mapping[str, Any]], *, limit: int) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in profile_items:
        category = str(item.get("category") or "").strip()
        if category not in _STABLE_PROFILE_CATEGORIES:
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


def _build_open_decisions(continuity_rows: Iterable[Mapping[str, Any]], *, limit: int) -> List[str]:
    return _unique_lines(
        (
            str(row.get("content") or "")
            for row in continuity_rows
            if str(row.get("kind") or "").strip() == "decision"
        ),
        limit=limit,
    )


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
    continuity_rows: Iterable[Mapping[str, Any]],
    lifecycle_state: Mapping[str, Any] | None,
    stable_profile_limit: int = 4,
    decision_limit: int = 4,
) -> Dict[str, Any]:
    continuity_list = [dict(row) for row in continuity_rows]
    stable_profile_entries = _build_stable_profile_entries(profile_items, limit=stable_profile_limit)
    active_work_summary = _build_active_work_summary(continuity_list)
    open_decisions = _build_open_decisions(continuity_list, limit=decision_limit)
    session_state = _build_session_state(lifecycle_state)
    external_owner_pointers: List[Dict[str, str]] = []
    proactive_guidance = ""
    if session_state["active"] and (active_work_summary or open_decisions):
        proactive_guidance = (
            "If the user re-engages vaguely, resume the active work or open decisions below before falling back to generic small talk. "
            "Do not invent reminders or take ownership of scheduling."
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
        "open_decisions": open_decisions,
        "open_decision_count": len(open_decisions),
        "session_state": session_state,
        "external_owner_pointers": external_owner_pointers,
        "external_owner_pointer_count": len(external_owner_pointers),
        "proactive_guidance": proactive_guidance,
        "owner_boundary": "Reminders, scheduling, and task truth stay with native owners; Brainstack carries context only.",
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
    open_decisions = _unique_lines(snapshot.get("open_decisions") or [], limit=4)
    stable_profile_entries = list(snapshot.get("stable_profile_entries") or [])
    session_state = snapshot.get("session_state") if isinstance(snapshot.get("session_state"), Mapping) else {}
    proactive_guidance = _normalize_text(snapshot.get("proactive_guidance"))
    owner_boundary = _normalize_text(snapshot.get("owner_boundary"))

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

    if open_decisions:
        decision_lines = ["", "Open decisions:"]
        for decision in open_decisions:
            decision_lines.append(f"- {_trim(decision, 180)}")
        content_added = _append_block(lines, decision_lines, char_budget=char_budget) or content_added

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
