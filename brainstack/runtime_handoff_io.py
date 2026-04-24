from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple


ACTIVE_TASK_STATUSES = {"pending", "queued", "open", "blocked", "in_progress"}
TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled", "stale"}
ALL_TASK_STATUSES = ACTIVE_TASK_STATUSES | TERMINAL_TASK_STATUSES


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _payload_hash(task_type: str, payload: Mapping[str, Any]) -> str:
    raw = f"{task_type}:{json.dumps(dict(payload), sort_keys=True, default=str)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def runtime_task_identity(raw: Mapping[str, Any]) -> str:
    payload = raw.get("payload") if isinstance(raw.get("payload"), Mapping) else {}
    task_type = _normalize_text(raw.get("type"))
    queue_id = _normalize_text(payload.get("queue_id")) if isinstance(payload, Mapping) else ""
    task_hash = _normalize_text(raw.get("task_hash"))
    if not task_hash and task_type and isinstance(payload, Mapping):
        task_hash = _payload_hash(task_type, payload)
    raw_id = _normalize_text(raw.get("id"))
    return queue_id or task_hash or raw_id


def _brainstack_home(hermes_home: Path) -> Path:
    return hermes_home / "home" / "brainstack"


def inbox_dir(hermes_home: Path) -> Path:
    return _brainstack_home(hermes_home) / "inbox"


def outbox_dir(hermes_home: Path) -> Path:
    return _brainstack_home(hermes_home) / "outbox"


def archive_dir(hermes_home: Path) -> Path:
    return _brainstack_home(hermes_home) / "archive"


def ensure_runtime_handoff_dirs(hermes_home: Path) -> None:
    for path in (inbox_dir(hermes_home), outbox_dir(hermes_home), archive_dir(hermes_home)):
        path.mkdir(parents=True, exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_task_record(path: Path) -> Dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def locate_task_record(hermes_home: Path, *, task_id: str) -> Tuple[Path | None, Dict[str, Any] | None]:
    normalized_task_id = _normalize_text(task_id)
    if not normalized_task_id:
        return None, None
    for directory in (inbox_dir(hermes_home), outbox_dir(hermes_home), archive_dir(hermes_home)):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            raw = load_task_record(path)
            if raw is None:
                continue
            if runtime_task_identity(raw) == normalized_task_id or _normalize_text(raw.get("id")) == normalized_task_id:
                return path, raw
    return None, None


def write_task_record(
    hermes_home: Path,
    *,
    record: Mapping[str, Any],
    status: str,
    current_path: Path | None = None,
) -> Path:
    ensure_runtime_handoff_dirs(hermes_home)
    normalized_status = _normalize_text(status).lower()
    target_dir = outbox_dir(hermes_home) if normalized_status in TERMINAL_TASK_STATUSES else inbox_dir(hermes_home)
    filename = current_path.name if current_path is not None else f"{_normalize_text(record.get('id')) or utc_now_iso().replace(':', '-')}.json"
    target_path = target_dir / filename
    payload = dict(record)
    payload["status"] = normalized_status
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if current_path is not None and current_path.resolve() != target_path.resolve():
        current_path.unlink(missing_ok=True)
    return target_path
