"""Durable runtime work-run spine for Hermes proactive handoffs.

This module is runtime support, not a scheduler. It records compact, public-safe
run state so a later agent can recover interrupted work without reading raw
transcripts or pretending a model process can resume bit-identically.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .config import proactive_state_base_dir


WORKRUN_SCHEMA = "hermes_proactive.workrun.v1"
WORKRUN_RECOVERY_CANDIDATE_SCHEMA = "hermes_proactive.workrun_recovery_candidate.v1"

RUNNING_STATES = {"queued", "claimed", "running", "checkpointed"}
RECOVERY_STATES = RUNNING_STATES | {"interrupted", "failed", "reclaimable"}
TERMINAL_STATES = {"completed", "cancelled"}
SOURCE_KINDS = {"cron", "proactive", "goal", "kanban", "process", "proactive_pulse"}
RISK_VALUES = {"none", "low", "medium", "high"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _compact_text(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _safe_id(value: Any, *, prefix: str = "run") -> str:
    text = _compact_text(value, limit=120)
    if not text:
        return prefix
    allowed = "".join(ch if ch.isalnum() or ch in {"-", "_", ":", "."} else "_" for ch in text)
    allowed = allowed.strip("._-:")
    if allowed:
        return allowed[:96]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(payload), ensure_ascii=True, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:24]


def workrun_dir(hermes_home: Path) -> Path:
    return proactive_state_base_dir(hermes_home) / "workruns"


def _path_for(hermes_home: Path, run_id: str) -> Path:
    return workrun_dir(hermes_home) / f"{_safe_id(run_id)}.json"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(dict(payload), ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _refs(values: Any, *, limit: int = 16) -> list[str]:
    if values is None:
        return []
    raw = values if isinstance(values, list | tuple | set) else [values]
    refs: list[str] = []
    for item in raw:
        ref = _compact_text(item, limit=180)
        if ref and ref not in refs:
            refs.append(ref)
        if len(refs) >= limit:
            break
    return refs


def build_run_id(*, source_kind: str, source_id: str, objective: str, started_at: str = "") -> str:
    kind = _safe_id(source_kind or "process", prefix="source")
    source = _safe_id(source_id or "unknown", prefix="source")
    digest = _digest({"source_kind": kind, "source_id": source, "objective": objective, "started_at": started_at})
    return f"{kind}:{source}:{digest}"


def start_workrun(
    *,
    hermes_home: Path,
    source_kind: str,
    source_id: str,
    objective: str,
    run_id: str = "",
    session_id: str = "",
    recovery_policy: str = "inspect_checkpoint_before_retry",
    side_effect_risk: str = "low",
    next_safe_action: str = "inspect latest checkpoint and decide whether retry is safe",
    checkpoint_refs: Any = None,
    output_refs: Any = None,
    metadata: Mapping[str, Any] | None = None,
    started_at: str = "",
    heartbeat_at: str = "",
) -> dict[str, Any]:
    started = started_at or _utc_now_iso()
    heartbeat = heartbeat_at or started
    safe_source_kind = source_kind if source_kind in SOURCE_KINDS else "process"
    safe_risk = side_effect_risk if side_effect_risk in RISK_VALUES else "medium"
    record = {
        "schema": WORKRUN_SCHEMA,
        "run_id": run_id or build_run_id(source_kind=safe_source_kind, source_id=source_id, objective=objective, started_at=started),
        "source_kind": safe_source_kind,
        "source_id": _compact_text(source_id, limit=160),
        "objective": _compact_text(objective, limit=320),
        "state": "running",
        "started_at": started,
        "heartbeat_at": heartbeat,
        "finished_at": "",
        "session_id": _compact_text(session_id, limit=160),
        "checkpoint_refs": _refs(checkpoint_refs),
        "output_refs": _refs(output_refs),
        "recovery_policy": _compact_text(recovery_policy, limit=180),
        "side_effect_risk": safe_risk,
        "next_safe_action": _compact_text(next_safe_action, limit=240),
        "metadata": {str(key): _compact_text(value, limit=160) for key, value in dict(metadata or {}).items()},
    }
    _atomic_write_json(_path_for(hermes_home, str(record["run_id"])), record)
    return record


def load_workrun(*, hermes_home: Path, run_id: str) -> dict[str, Any]:
    return _read_json(_path_for(hermes_home, run_id))


def update_workrun(
    *,
    hermes_home: Path,
    run_id: str,
    state: str | None = None,
    checkpoint_refs: Any = None,
    output_refs: Any = None,
    next_safe_action: str = "",
    error_summary: str = "",
    heartbeat_at: str = "",
    finished_at: str = "",
) -> dict[str, Any]:
    record = load_workrun(hermes_home=hermes_home, run_id=run_id)
    if not record:
        return {}
    if state:
        record["state"] = _compact_text(state, limit=40)
    if heartbeat_at or state in RUNNING_STATES:
        record["heartbeat_at"] = heartbeat_at or _utc_now_iso()
    if checkpoint_refs is not None:
        record["checkpoint_refs"] = _refs([*list(record.get("checkpoint_refs") or []), *_refs(checkpoint_refs)])
    if output_refs is not None:
        record["output_refs"] = _refs([*list(record.get("output_refs") or []), *_refs(output_refs)])
    if next_safe_action:
        record["next_safe_action"] = _compact_text(next_safe_action, limit=240)
    if error_summary:
        record["error_summary"] = _compact_text(error_summary, limit=240)
    if finished_at or state in TERMINAL_STATES or state in {"failed", "interrupted"}:
        record["finished_at"] = finished_at or _utc_now_iso()
    _atomic_write_json(_path_for(hermes_home, run_id), record)
    return record


def checkpoint_workrun(*, hermes_home: Path, run_id: str, checkpoint_ref: str, next_safe_action: str = "") -> dict[str, Any]:
    return update_workrun(
        hermes_home=hermes_home,
        run_id=run_id,
        state="checkpointed",
        checkpoint_refs=[checkpoint_ref],
        next_safe_action=next_safe_action,
    )


def finish_workrun(
    *,
    hermes_home: Path,
    run_id: str,
    status: str = "completed",
    output_ref: str = "",
    error_summary: str = "",
    next_safe_action: str = "",
) -> dict[str, Any]:
    state = status if status in TERMINAL_STATES or status in {"failed", "interrupted"} else "failed"
    return update_workrun(
        hermes_home=hermes_home,
        run_id=run_id,
        state=state,
        output_refs=[output_ref] if output_ref else None,
        error_summary=error_summary,
        next_safe_action=next_safe_action,
        finished_at=_utc_now_iso(),
    )


def list_workruns(*, hermes_home: Path, limit: int = 200) -> list[dict[str, Any]]:
    base = workrun_dir(hermes_home)
    if not base.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        row = _read_json(path)
        if row.get("schema") == WORKRUN_SCHEMA:
            rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def recovery_card(record: Mapping[str, Any], *, now: datetime | None = None, stale_after_seconds: int = 600) -> dict[str, Any] | None:
    state = str(record.get("state") or "")
    if state in TERMINAL_STATES:
        return None
    heartbeat = _parse_iso(record.get("heartbeat_at")) or _parse_iso(record.get("started_at"))
    current = now or datetime.now(timezone.utc)
    stale = True
    age_seconds = 0
    if heartbeat is not None:
        age_seconds = max(0, int((current - heartbeat).total_seconds()))
        stale = age_seconds >= max(1, int(stale_after_seconds or 1))
    if state in RUNNING_STATES and not stale:
        return None
    recovery_state = "reclaimable" if state in RUNNING_STATES else state
    return {
        "schema": WORKRUN_RECOVERY_CANDIDATE_SCHEMA,
        "run_id": _compact_text(record.get("run_id"), limit=160),
        "source_kind": _compact_text(record.get("source_kind"), limit=40),
        "source_id": _compact_text(record.get("source_id"), limit=160),
        "objective": _compact_text(record.get("objective"), limit=320),
        "state": recovery_state,
        "started_at": _compact_text(record.get("started_at"), limit=80),
        "heartbeat_at": _compact_text(record.get("heartbeat_at"), limit=80),
        "age_seconds": age_seconds,
        "checkpoint_refs": _refs(record.get("checkpoint_refs"), limit=8),
        "output_refs": _refs(record.get("output_refs"), limit=8),
        "recovery_policy": _compact_text(record.get("recovery_policy"), limit=180),
        "side_effect_risk": _compact_text(record.get("side_effect_risk"), limit=40) or "medium",
        "next_safe_action": _compact_text(record.get("next_safe_action"), limit=240),
    }


def list_recovery_candidates(*, hermes_home: Path, stale_after_seconds: int = 600, limit: int = 20) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    candidates: list[dict[str, Any]] = []
    for record in list_workruns(hermes_home=hermes_home, limit=max(limit * 10, 50)):
        card = recovery_card(record, now=now, stale_after_seconds=stale_after_seconds)
        if card is not None:
            candidates.append(card)
        if len(candidates) >= limit:
            break
    return candidates


def prune_completed_workruns(*, hermes_home: Path, keep_completed: int = 200) -> dict[str, Any]:
    completed: list[Path] = []
    for path in sorted(workrun_dir(hermes_home).glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        record = _read_json(path)
        if str(record.get("state") or "") in TERMINAL_STATES:
            completed.append(path)
    removed = 0
    for path in completed[max(0, int(keep_completed or 0)):]:
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return {"schema": "hermes_proactive.workrun_prune.v1", "completed_seen": len(completed), "removed": removed}
