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


PULSE_PRODUCER_SCHEMA = "hermes_proactive.pulse_producer.v1"


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


def _runtime_handoff_summary(hermes_home: Path) -> dict[str, int]:
    base = _brainstack_home(hermes_home)
    return {
        "inbox_count": len(list((base / "inbox").glob("*.json"))) if (base / "inbox").exists() else 0,
        "outbox_count": len(list((base / "outbox").glob("*.json"))) if (base / "outbox").exists() else 0,
        "archive_count": len(list((base / "archive").glob("*.json"))) if (base / "archive").exists() else 0,
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
    evolver_health = _read_json(evolver_health_file)

    if not bool(evolver_health.get("running", True)):
        tasks.append(
            _candidate(
                source="evolver",
                kind=ProactiveEventKind.EVOLVER_CANDIDATE.value,
                title="Evolver is not running",
                summary="Evolver health reports stopped or unavailable state.",
                priority="high",
                evidence_ids=["evolver:health"],
                intended_next_action=ProactiveIntendedNextAction.ASK_PERMISSION.value,
                source_ref=str(evolver_health_file or ""),
                metadata={"evolver_health": evolver_health},
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
    }


def project_pulse_output(*, db_path: Path, output: Mapping[str, Any], create_outbox: bool) -> dict[str, Any]:
    store = BrainstackStore(str(db_path))
    store.open()
    try:
        projection = StoreProactiveProjection(store)
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
            if create_outbox and not output.get("no_op"):
                outbox.append(
                    projection.create_outbox(
                        event_id=str(event["event_id"]),
                        delivery_target="proactive_runtime",
                        intended_next_action=str(event.get("intended_next_action") or ProactiveIntendedNextAction.NONE.value),
                    )
                )
        return {"schema": "hermes_proactive.pulse_projection.v1", "written_count": len(written), "outbox_count": len(outbox), "written": written, "outbox": outbox}
    finally:
        store.close()
