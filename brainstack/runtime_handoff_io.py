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


def summarize_runtime_handoff_dirs(hermes_home: Path, *, sample_limit: int = 6) -> Dict[str, Any]:
    """Return bounded read-only queue health without executing or deleting tasks."""
    summary: Dict[str, Any] = {
        "schema": "brainstack.runtime_handoff_dirs.v1",
        "inbox_count": 0,
        "outbox_count": 0,
        "archive_count": 0,
        "invalid_json_count": 0,
        "duplicate_identity_count": 0,
        "inbox_duplicate_identity_count": 0,
        "duplicate_identity_counts_by_directory": {},
        "status_counts": {},
        "status_counts_by_directory": {},
        "type_counts": {},
        "type_counts_by_directory": {},
        "samples": [],
    }
    seen_identities: set[str] = set()
    duplicate_identities: set[str] = set()
    duplicate_identities_by_directory: dict[str, set[str]] = {}
    samples: list[Dict[str, Any]] = []
    directories = {
        "inbox": inbox_dir(hermes_home),
        "outbox": outbox_dir(hermes_home),
        "archive": archive_dir(hermes_home),
    }
    for directory_name, directory in directories.items():
        directory_seen_identities: set[str] = set()
        directory_duplicate_identities: set[str] = set()
        directory_status_counts: dict[str, int] = {}
        directory_type_counts: dict[str, int] = {}
        if not directory.exists():
            continue
        paths = sorted(directory.glob("*.json"))
        summary[f"{directory_name}_count"] = len(paths)
        for path in paths:
            raw = load_task_record(path)
            if raw is None:
                summary["invalid_json_count"] = int(summary["invalid_json_count"]) + 1
                continue
            identity = runtime_task_identity(raw)
            if identity:
                if identity in seen_identities:
                    duplicate_identities.add(identity)
                seen_identities.add(identity)
                if identity in directory_seen_identities:
                    directory_duplicate_identities.add(identity)
                directory_seen_identities.add(identity)
            status = _normalize_text(raw.get("status")).lower() or "unknown"
            task_type = _normalize_text(raw.get("type")) or "unknown"
            status_counts = dict(summary["status_counts"])
            type_counts = dict(summary["type_counts"])
            status_counts[status] = int(status_counts.get(status, 0)) + 1
            type_counts[task_type] = int(type_counts.get(task_type, 0)) + 1
            directory_status_counts[status] = int(directory_status_counts.get(status, 0)) + 1
            directory_type_counts[task_type] = int(directory_type_counts.get(task_type, 0)) + 1
            summary["status_counts"] = status_counts
            summary["type_counts"] = type_counts
            if len(samples) < max(int(sample_limit or 0), 0):
                raw_payload = raw.get("payload")
                payload: Mapping[str, Any] = raw_payload if isinstance(raw_payload, Mapping) else {}
                samples.append(
                    {
                        "directory": directory_name,
                        "filename": path.name,
                        "identity": identity,
                        "status": status,
                        "type": task_type,
                        "title": _normalize_text(
                            payload.get("title")
                            or payload.get("task")
                            or payload.get("message")
                            or raw.get("title")
                            or raw.get("id")
                        )[:180],
                    }
                )
        duplicate_identities_by_directory[directory_name] = directory_duplicate_identities
        status_counts_by_directory = dict(summary["status_counts_by_directory"])
        type_counts_by_directory = dict(summary["type_counts_by_directory"])
        status_counts_by_directory[directory_name] = directory_status_counts
        type_counts_by_directory[directory_name] = directory_type_counts
        summary["status_counts_by_directory"] = status_counts_by_directory
        summary["type_counts_by_directory"] = type_counts_by_directory
    summary["duplicate_identity_count"] = len(duplicate_identities)
    summary["duplicate_identity_counts_by_directory"] = {
        directory_name: len(identities)
        for directory_name, identities in sorted(duplicate_identities_by_directory.items())
    }
    summary["inbox_duplicate_identity_count"] = int(
        summary["duplicate_identity_counts_by_directory"].get("inbox", 0)
    )
    summary["samples"] = samples
    return summary


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
