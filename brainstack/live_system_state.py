from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Mapping


LIVE_SYSTEM_STATE_OWNER = "brainstack.live_system_state"
LIVE_SYSTEM_STATE_RECORD_TYPE = "live_system_state"
LIVE_SYSTEM_STATE_SNAPSHOT_VERSION = 1

logger = logging.getLogger(__name__)
QUERY_TOKEN_RE = re.compile(r"[^\W_]+(?:[-_][^\W_]+)*", re.UNICODE)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _get_hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home()).resolve()
    except Exception:
        env_home = str(os.getenv("HERMES_HOME") or "").strip()
        if env_home:
            return Path(env_home).expanduser().resolve()
        return (Path.home() / ".hermes").resolve()


def _jobs_file_path() -> Path:
    return _get_hermes_home() / "cron" / "jobs.json"


def _normalize_jobs_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        raw_jobs = payload.get("jobs")
        if isinstance(raw_jobs, list):
            return [dict(item) for item in raw_jobs if isinstance(item, Mapping)]
    return []


def _load_jobs_payload() -> tuple[List[Dict[str, Any]], str]:
    jobs_path = _jobs_file_path()
    if not jobs_path.exists():
        return [], ""
    try:
        payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("Brainstack live system state could not read jobs.json: %s", exc)
        return [], ""
    updated_at = ""
    if isinstance(payload, Mapping):
        updated_at = _normalize_text(payload.get("updated_at"))
    if not updated_at:
        try:
            updated_at = datetime.fromtimestamp(jobs_path.stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            updated_at = ""
    return _normalize_jobs_payload(payload), updated_at


def _schedule_summary(schedule: Any) -> str:
    if not isinstance(schedule, Mapping):
        return ""
    display = _normalize_text(schedule.get("display"))
    expr = _normalize_text(schedule.get("expr"))
    kind = _normalize_text(schedule.get("kind"))
    if display:
        return display
    if expr:
        return expr
    return kind


def _cron_job_rows(*, principal_scope_key: str) -> List[Dict[str, Any]]:
    jobs, updated_at = _load_jobs_payload()
    active_jobs = [
        dict(job)
        for job in jobs
        if bool(job.get("enabled", True))
        and _normalize_text(job.get("state")).casefold() not in {"disabled", "completed", "removed"}
    ]
    timestamp = updated_at or _utc_now_iso()
    if not active_jobs:
        return [
            {
                "id": 0,
                "stable_key": "live_system_state::cron_scheduler::absent",
                "principal_scope_key": principal_scope_key,
                "record_type": LIVE_SYSTEM_STATE_RECORD_TYPE,
                "content": "No Hermes scheduler jobs are currently present in live runtime state.",
                "owner": LIVE_SYSTEM_STATE_OWNER,
                "source": "live_runtime:cron_scheduler",
                "source_session_id": "",
                "source_turn_number": 0,
                "metadata": {
                    "provider": "cron_scheduler",
                    "state": "absent",
                    "authoritative_current": True,
                    "live_runtime": True,
                },
                "created_at": timestamp,
                "updated_at": timestamp,
                "confidence": 1.0,
                "retrieval_source": "live_system_state.cron_scheduler",
                "match_mode": "authority",
            }
        ]
    rows: List[Dict[str, Any]] = []
    for index, job in enumerate(active_jobs, start=1):
        job_id = _normalize_text(job.get("id")) or f"cron-job-{index}"
        job_name = _normalize_text(job.get("name")) or job_id
        job_state = _normalize_text(job.get("state")) or "scheduled"
        schedule_text = _schedule_summary(job.get("schedule"))
        status_text = f"Hermes scheduler job '{job_name}' is {job_state}"
        if schedule_text:
            status_text += f" ({schedule_text})"
        status_text += "."
        rows.append(
            {
                "id": 0,
                "stable_key": f"live_system_state::cron_scheduler::{job_id}",
                "principal_scope_key": principal_scope_key,
                "record_type": LIVE_SYSTEM_STATE_RECORD_TYPE,
                "content": status_text,
                "owner": LIVE_SYSTEM_STATE_OWNER,
                "source": "live_runtime:cron_scheduler",
                "source_session_id": "",
                "source_turn_number": 0,
                "metadata": {
                    "provider": "cron_scheduler",
                    "job_id": job_id,
                    "job_name": job_name,
                    "job_state": job_state,
                    "schedule": job.get("schedule") if isinstance(job.get("schedule"), Mapping) else {},
                    "authoritative_current": True,
                    "live_runtime": True,
                },
                "created_at": timestamp,
                "updated_at": timestamp,
                "confidence": 1.0,
                "retrieval_source": "live_system_state.cron_scheduler",
                "match_mode": "authority",
            }
        )
    return rows


def list_live_system_state_rows(*, principal_scope_key: str, limit: int = 8) -> List[Dict[str, Any]]:
    rows = _cron_job_rows(principal_scope_key=principal_scope_key)
    return rows[: max(int(limit or 0), 1)]


def build_live_system_state_snapshot(*, principal_scope_key: str, limit: int = 8) -> Dict[str, Any]:
    rows = list_live_system_state_rows(principal_scope_key=principal_scope_key, limit=limit)
    authoritative_sources = []
    seen: set[str] = set()
    for row in rows:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
        provider = _normalize_text((metadata or {}).get("provider"))
        if not provider or provider in seen:
            continue
        seen.add(provider)
        authoritative_sources.append(provider)
    return {
        "snapshot_version": LIVE_SYSTEM_STATE_SNAPSHOT_VERSION,
        "principal_scope_key": str(principal_scope_key or "").strip(),
        "rows": rows,
        "row_count": len(rows),
        "authoritative_sources": authoritative_sources,
        "authoritative": bool(rows),
    }


def search_live_system_state_rows(
    *,
    query: str,
    principal_scope_key: str,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    rows = list_live_system_state_rows(principal_scope_key=principal_scope_key, limit=max(limit * 4, 8))
    query_terms = {
        token
        for token in re.findall(QUERY_TOKEN_RE, _normalize_text(query).casefold())
        if len(token) >= 3
    }
    if not query_terms:
        return rows[: max(int(limit or 0), 1)]
    ranked: List[Dict[str, Any]] = []
    for row in rows:
        haystack = _normalize_text(row.get("content")).casefold()
        overlap = sum(1 for token in query_terms if token in haystack)
        if overlap <= 0:
            continue
        payload = dict(row)
        payload["keyword_score"] = max(float(payload.get("keyword_score") or 0.0), float(overlap))
        ranked.append(payload)
    if not ranked:
        return []
    ranked.sort(
        key=lambda item: (
            float(item.get("keyword_score") or 0.0),
            str(item.get("updated_at") or ""),
            str(item.get("stable_key") or ""),
        ),
        reverse=True,
    )
    return ranked[: max(int(limit or 0), 1)]
