"""Deterministic PulseProducer for the optional Hermes proactive extension."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from brainstack.db import BrainstackStore
from brainstack.sdk.proactive import (
    ProactiveEventKind,
    ProactiveIntendedNextAction,
    StoreProactiveProjection,
)

from .evolver_signal import load_evolver_signal_file
from .heartbeat_wake import (
    HEARTBEAT_WAKE_SCHEMA,
    HeartbeatWakeDecision,
    HeartbeatWakeRequest,
    HeartbeatWakeState,
    classify_heartbeat_wake,
)
from .workrun import list_recovery_candidates


PULSE_PRODUCER_SCHEMA = "hermes_proactive.pulse_producer.v1"
PULSE_WAKE_SCHEMA = "hermes_proactive.pulse_wake.v1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_key(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(payload), ensure_ascii=True, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _brainstack_home(hermes_home: Path) -> Path:
    return hermes_home / "home" / "brainstack"


def _bounded_json_count(path: Path, *, limit: int = 1000) -> tuple[int, bool]:
    if not path.exists() or not path.is_dir():
        return 0, False
    count = 0
    try:
        for item in path.glob("*.json"):
            if not item.is_file():
                continue
            count += 1
            if count >= limit:
                return count, True
    except OSError:
        return count, True
    return count, False


def _bounded_json_count(path: Path, *, limit: int = 1000) -> tuple[int, bool]:
    if not path.exists() or not path.is_dir():
        return 0, False
    count = 0
    try:
        for item in path.glob("*.json"):
            if not item.is_file():
                continue
            count += 1
            if count >= limit:
                return count, True
    except OSError:
        return count, True
    return count, False

def _runtime_handoff_summary(hermes_home: Path) -> dict[str, int | bool]:
    base = _brainstack_home(hermes_home)
    inbox_count, inbox_truncated = _bounded_json_count(base / "inbox")
    outbox_count, outbox_truncated = _bounded_json_count(base / "outbox")
    archive_count, archive_truncated = _bounded_json_count(base / "archive")
    return {
        "inbox_count": inbox_count,
        "outbox_count": outbox_count,
        "archive_count": archive_count,
        "inbox_truncated": inbox_truncated,
        "outbox_truncated": outbox_truncated,
        "archive_truncated": archive_truncated,
    }


def _candidate(
    *,
    source: str,
    kind: str,
    title: str,
    summary: str,
    priority: str,
    evidence_ids: list[str],
    intended_next_action: str,
    source_ref: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "source": source,
        "kind": kind,
        "title": title,
        "summary": summary,
        "priority": priority,
        "evidence_ids": evidence_ids,
        "intended_next_action": intended_next_action,
        "source_ref": source_ref,
        "metadata": dict(metadata or {}),
    }
    payload["candidate_key"] = _stable_key(payload)
    payload["material_change"] = True
    return payload


def produce_pulse(
    *,
    hermes_home: Path,
    principal_scope_key: str,
    workspace_scope_key: str,
    workstream_scope_key: str = "",
    evolver_health_file: Path | None = None,
    stale_inbox_threshold: int = 1,
) -> dict[str, Any]:
    started = _utc_now_iso()
    tasks: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    handoff = _runtime_handoff_summary(hermes_home)
    evolver_signal = load_evolver_signal_file(evolver_health_file) if evolver_health_file is not None else None
    workrun_recovery = list_recovery_candidates(hermes_home=hermes_home, stale_after_seconds=600, limit=5)

    if evolver_signal is not None and evolver_signal.actionable:
        signal = evolver_signal.to_public_dict()
        tasks.append(
            _candidate(
                source="evolver",
                kind=ProactiveEventKind.EVOLVER_CANDIDATE.value,
                title="Evolver signal needs attention",
                summary=str(signal.get("safe_summary") or "Evolver emitted an actionable signal."),
                priority="high" if signal.get("status") in {"stopped", "malformed"} else "normal",
                evidence_ids=[f"evolver:{signal.get('reason_code') or 'signal'}"],
                intended_next_action=ProactiveIntendedNextAction.ASK_PERMISSION.value,
                source_ref=str(evolver_health_file or ""),
                metadata={"evolver_signal": signal},
            )
        )

    inbox_count = int(handoff.get("inbox_count") or 0)
    if inbox_count >= max(1, int(stale_inbox_threshold or 1)):
        tasks.append(
            _candidate(
                source="runtime_handoff",
                kind=ProactiveEventKind.INBOX_ITEM.value,
                title="Runtime inbox has pending items",
                summary=f"{inbox_count} runtime handoff item(s) are pending.",
                priority="normal",
                evidence_ids=["runtime_handoff:inbox"],
                intended_next_action=ProactiveIntendedNextAction.INFORM_USER.value,
                metadata={"handoff_summary": handoff},
            )
        )

    for card in workrun_recovery:
        run_id = str(card.get("run_id") or "")
        risk = str(card.get("side_effect_risk") or "medium")
        tasks.append(
            _candidate(
                source="workrun_recovery",
                kind=ProactiveEventKind.BLOCKED.value if risk in {"medium", "high"} else ProactiveEventKind.FOLLOW_UP.value,
                title="Interrupted runtime work needs recovery review",
                summary=(
                    f"{str(card.get('source_kind') or 'process')} work '{str(card.get('source_id') or run_id)}' "
                    f"is {str(card.get('state') or 'reclaimable')}; next safe action: "
                    f"{str(card.get('next_safe_action') or 'inspect checkpoint before retry')}."
                ),
                priority="high" if risk in {"medium", "high"} else "normal",
                evidence_ids=[f"workrun:{run_id}"] if run_id else ["workrun:recovery"],
                intended_next_action=ProactiveIntendedNextAction.ASK_PERMISSION.value,
                source_ref=run_id,
                metadata={"workrun_recovery": card},
            )
        )

    if not tasks:
        events.append(
            _candidate(
                source="heartbeat",
                kind=ProactiveEventKind.HEARTBEAT_OK.value,
                title="Heartbeat healthy",
                summary="No actionable proactive item found.",
                priority="low",
                evidence_ids=["heartbeat:ok"],
                intended_next_action=ProactiveIntendedNextAction.NONE.value,
            )
        )

    return {
        "schema": PULSE_PRODUCER_SCHEMA,
        "run_id": "pulse_" + _stable_key({"started": started, "home": str(hermes_home)}),
        "started_at": started,
        "finished_at": _utc_now_iso(),
        "status": "no_op" if not tasks else "actionable",
        "events": events,
        "tasks": tasks,
        "candidate_count": len(events) + len(tasks),
        "outbox_count": 0,
        "no_op": not tasks,
        "provider_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "delivery_requested": False,
        "principal_scope_key": principal_scope_key,
        "workspace_scope_key": workspace_scope_key,
        "workstream_scope_key": workstream_scope_key,
        "workrun_recovery_count": len(workrun_recovery),
    }


def _pulse_wake_key(output: Mapping[str, Any]) -> str:
    task_keys = [str(item.get("candidate_key") or "") for item in output.get("tasks") or [] if isinstance(item, Mapping)]
    return "pulse:" + _stable_key(
        {
            "principal_scope_key": str(output.get("principal_scope_key") or ""),
            "workspace_scope_key": str(output.get("workspace_scope_key") or ""),
            "workstream_scope_key": str(output.get("workstream_scope_key") or ""),
            "task_keys": task_keys,
        }
    )


def classify_pulse_wake(
    output: Mapping[str, Any],
    *,
    create_outbox: bool,
    target: str = "proactive_runtime",
    wake_state: HeartbeatWakeState | None = None,
) -> dict[str, Any]:
    """Classify whether a pulse should request Hermes-owned delivery."""

    task_count = len([item for item in output.get("tasks") or [] if isinstance(item, Mapping)])
    key = _pulse_wake_key(output)
    base = {
        "schema": PULSE_WAKE_SCHEMA,
        "heartbeat_schema": HEARTBEAT_WAKE_SCHEMA,
        "idempotency_key": key,
        "target": target,
        "task_count": task_count,
        "provider_calls": 0,
        "transcript_writes": 0,
    }
    if bool(output.get("no_op")) or task_count == 0:
        return {
            **base,
            "decision": "no_op",
            "reason_code": "NO_ACTIONABLE_ITEM",
            "delivery_requested": False,
            "retry_after_seconds": None,
            "stale_lock_cancelled": False,
        }
    if not create_outbox:
        return {
            **base,
            "decision": "observed",
            "reason_code": "WAKE_NOT_REQUESTED",
            "delivery_requested": False,
            "retry_after_seconds": None,
            "stale_lock_cancelled": False,
        }
    result = classify_heartbeat_wake(
        HeartbeatWakeRequest(
            target=target,
            source="pulse",
            run_id=str(output.get("run_id") or ""),
            idempotency_key=key,
            metadata={"task_count": str(task_count)},
        ),
        wake_state or HeartbeatWakeState(),
    ).to_dict()
    decision = str(result.get("decision") or "")
    delivery_requested = decision in {HeartbeatWakeDecision.READY.value, HeartbeatWakeDecision.STALE_CANCELLED.value}
    return {
        **base,
        **result,
        "schema": PULSE_WAKE_SCHEMA,
        "heartbeat_schema": HEARTBEAT_WAKE_SCHEMA,
        "task_count": task_count,
        "delivery_requested": delivery_requested,
        "provider_calls": 0,
        "transcript_writes": 0,
    }


def project_pulse_output(
    *,
    db_path: Path,
    output: Mapping[str, Any],
    create_outbox: bool,
    delivery_target: str = "proactive_runtime",
    wake_state: HeartbeatWakeState | None = None,
) -> dict[str, Any]:
    store = BrainstackStore(str(db_path))
    store.open()
    try:
        projection = StoreProactiveProjection(store)
        wake = classify_pulse_wake(
            output,
            create_outbox=create_outbox,
            target=delivery_target,
            wake_state=wake_state,
        )
        written: list[dict[str, Any]] = []
        outbox: list[dict[str, Any]] = []
        for item in [*list(output.get("events") or []), *list(output.get("tasks") or [])]:
            if not isinstance(item, Mapping):
                continue
            event = projection.project_event(
                source=str(item.get("source") or "pulse"),
                kind=str(item.get("kind") or ProactiveEventKind.FOLLOW_UP.value),
                principal_scope_key=str(output.get("principal_scope_key") or ""),
                workspace_scope_key=str(output.get("workspace_scope_key") or ""),
                workstream_scope_key=str(output.get("workstream_scope_key") or ""),
                title=str(item.get("title") or ""),
                summary=str(item.get("summary") or ""),
                priority=str(item.get("priority") or "normal"),
                evidence_ids=[str(value) for value in item.get("evidence_ids") or []],
                source_ref=str(item.get("source_ref") or ""),
                idempotency_key=str(item.get("candidate_key") or ""),
                intended_next_action=str(item.get("intended_next_action") or ProactiveIntendedNextAction.NONE.value),
                metadata={
                    **dict(item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}),
                    "provider_calls": int(output.get("provider_calls") or 0),
                    "prompt_tokens": int(output.get("prompt_tokens") or 0),
                    "completion_tokens": int(output.get("completion_tokens") or 0),
                },
                trace_id=str(output.get("run_id") or ""),
            )
            written.append(event)
            if bool(wake.get("delivery_requested")):
                outbox.append(
                    projection.create_outbox(
                        event_id=str(event["event_id"]),
                        delivery_target=delivery_target,
                        idempotency_key=f"{wake.get('idempotency_key')}:{event['event_id']}",
                        intended_next_action=str(event.get("intended_next_action") or ProactiveIntendedNextAction.NONE.value),
                    )
                )
        return {
            "schema": "hermes_proactive.pulse_projection.v1",
            "written_count": len(written),
            "outbox_count": len(outbox),
            "wake": wake,
            "written": written,
            "outbox": outbox,
        }
    finally:
        store.close()
