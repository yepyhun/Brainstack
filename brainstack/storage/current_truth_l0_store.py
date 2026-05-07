from __future__ import annotations

import json
from typing import Any, Mapping

from .store_runtime import _locked, utc_now_iso
from ..core.reason_codes import ReasonCode
from ..current_truth_view import (
    CURRENT_TRUTH_VIEW_PROJECTION_VERSION,
    CURRENT_TRUTH_VIEW_SCHEMA_VERSION,
    rebuild_current_truth_view,
    validate_current_truth_view_public_safety,
)

_COUNTER_KEYS = (
    "input_event_count",
    "current_answerable_count",
    "non_answerable_count",
    "invalid_canonical_event_count",
    "prior_count",
    "conflict_count",
    "missing_source_count",
    "missing_receipt_count",
    "support_only_count",
    "stale_projection_source_count",
    "malformed_projection_count",
    "unsafe_answer_truth_projection_count",
    "stale_cache_serving_block_count",
    "second_write_authority_count",
    "raw_truth_write_attempt_count",
    "raw_text_leak_count",
)
_GRAPH_MEMORY_KINDS = frozenset({"graph_relation", "graph_state", "temporal_event"})
_ANSWER_SAFE_REASON = ReasonCode.PROJECTION_ANSWER_SAFE_CURRENT_SOURCE_BACKED.value
_PRIOR_SUPERSEDED_REASON = ReasonCode.PROJECTION_PRIOR_SUPERSEDED.value
_NOT_ANSWERABLE_PRIOR_REASON = ReasonCode.PROJECTION_NOT_ANSWERABLE_PRIOR.value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _loads_mapping(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _empty_counters() -> dict[str, int]:
    return {key: 0 for key in _COUNTER_KEYS}


def _row_scope(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(row.get("scope"))


def _row_sort_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    scope = _row_scope(row)
    return (
        _text(scope.get("principal_scope_key")),
        _text(row.get("stable_fact_id")),
        _text(row.get("event_id")),
    )


def _snapshot_hash(value: Any, *, length: int = 32) -> str:
    import hashlib

    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _canonical_rows_chronological(rows: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            _text(row.get("created_at")),
            int(row.get("id") or 0),
            _text(row.get("event_id")),
        ),
    )


class CurrentTruthL0StoreMixin:
    def _project_current_truth_l0_event(
        self,
        event: Mapping[str, Any],
        *,
        projected_at: str,
    ) -> list[dict[str, Any]]:
        view = rebuild_current_truth_view([event], rebuilt_at=projected_at, checked_at=projected_at)
        issues_by_event = {
            _text(issue.get("event_id")): issue
            for issue in _list(view.get("issues"))
            if isinstance(issue, Mapping)
        }
        counter_json = json.dumps(view.get("counters") or {}, ensure_ascii=True, sort_keys=True)
        event_group = _mapping(event.get("event"))
        projection = _mapping(event.get("projection"))
        hints = _mapping(projection.get("projection_hints"))
        graph_ready = bool(hints.get("graph_ready"))
        output: list[dict[str, Any]] = []
        for row_type, rows in (
            ("current_truth", _list(view.get("current_truth_rows"))),
            ("non_answerable", _list(view.get("non_answerable_rows"))),
        ):
            for raw_row in rows:
                if not isinstance(raw_row, Mapping):
                    continue
                row = dict(raw_row)
                event_id = _text(row.get("event_id"))
                issue = issues_by_event.get(event_id, {})
                output.append(
                    {
                        "row": row,
                        "row_type": row_type,
                        "graph_ready": graph_ready,
                        "issue_json": json.dumps(issue, ensure_ascii=True, sort_keys=True),
                        "counter_json": counter_json,
                        "event_type": _text(event_group.get("event_type")),
                    }
                )
        return output

    def _mark_l0_superseded_events(
        self,
        event: Mapping[str, Any],
        *,
        superseded_by_event_id: str,
        projected_at: str,
    ) -> None:
        prior_event_ids = [
            _text(item)
            for item in _list(_mapping(event.get("temporal")).get("supersedes"))
            if _text(item)
        ]
        if not prior_event_ids or not superseded_by_event_id:
            return
        placeholders = ",".join("?" for _ in prior_event_ids)
        rows = self.conn.execute(
            f"""
            SELECT event_id, row_json, issue_json, counter_json
            FROM current_truth_l0_rows
            WHERE event_id IN ({placeholders})
            """,
            tuple(prior_event_ids),
        ).fetchall()
        for raw in rows:
            row = _loads_mapping(raw["row_json"])
            counters = _loads_mapping(raw["counter_json"])
            existing_reasons = [
                reason
                for reason in (_text(reason) for reason in _list(row.get("projection_reason_codes")))
                if reason and reason not in {_ANSWER_SAFE_REASON, _PRIOR_SUPERSEDED_REASON, _NOT_ANSWERABLE_PRIOR_REASON}
            ]
            reason_codes = list(dict.fromkeys([_PRIOR_SUPERSEDED_REASON, _NOT_ANSWERABLE_PRIOR_REASON, *existing_reasons]))
            row.update(
                {
                    "answerable_current_truth": False,
                    "is_current": False,
                    "is_prior": True,
                    "superseded_by": superseded_by_event_id,
                    "projection_reason_codes": reason_codes,
                }
            )
            counters["current_answerable_count"] = 0
            counters["non_answerable_count"] = max(1, int(counters.get("non_answerable_count") or 0))
            counters["prior_count"] = max(1, int(counters.get("prior_count") or 0))
            counters["unsafe_answer_truth_projection_count"] = 0
            self.conn.execute(
                """
                UPDATE current_truth_l0_rows
                SET row_type = 'non_answerable',
                    answerable_current_truth = 0,
                    is_current = 0,
                    is_prior = 1,
                    superseded_by = ?,
                    row_json = ?,
                    counter_json = ?,
                    projected_at = ?
                WHERE event_id = ?
                """,
                (
                    superseded_by_event_id,
                    json.dumps(row, ensure_ascii=True, sort_keys=True),
                    json.dumps(counters, ensure_ascii=True, sort_keys=True),
                    projected_at,
                    str(raw["event_id"] or ""),
                ),
            )

    def _upsert_current_truth_l0_from_event(
        self,
        event: Mapping[str, Any],
        *,
        projected_at: str | None = None,
    ) -> None:
        event_id = _text(_mapping(event.get("event")).get("event_id"))
        if not event_id:
            return
        timestamp = _text(projected_at) or utc_now_iso()
        projected_rows = self._project_current_truth_l0_event(event, projected_at=timestamp)
        self.conn.execute("DELETE FROM current_truth_l0_rows WHERE event_id = ?", (event_id,))
        for projected in projected_rows:
            row = dict(projected["row"])
            scope = _row_scope(row)
            self.conn.execute(
                """
                INSERT OR REPLACE INTO current_truth_l0_rows (
                    view_id, event_id, stable_fact_id, target_slot, principal_scope_key,
                    workspace_scope_key, session_id, memory_kind, row_type,
                    answerable_current_truth, is_current, is_prior, is_conflicted,
                    is_support_only, is_retrieval_only, is_hidden, is_authority_critical,
                    graph_ready, source_event_id, source_span_id, source_quote_hash,
                    receipt_id, authority_class, truth_eligible, support_visibility,
                    valid_from, valid_to, transaction_time, superseded_by, projection_version,
                    row_json, issue_json, counter_json, projected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _text(row.get("view_id")),
                    _text(row.get("event_id")),
                    _text(row.get("stable_fact_id")),
                    _text(row.get("target_slot")),
                    _text(scope.get("principal_scope_key")),
                    _text(scope.get("workspace_scope_key")),
                    _text(scope.get("session_id")),
                    _text(row.get("memory_kind")),
                    str(projected["row_type"]),
                    1 if bool(row.get("answerable_current_truth")) else 0,
                    1 if bool(row.get("is_current")) else 0,
                    1 if bool(row.get("is_prior")) else 0,
                    1 if bool(row.get("is_conflicted")) else 0,
                    1 if bool(row.get("is_support_only")) else 0,
                    1 if bool(row.get("is_retrieval_only")) else 0,
                    1 if bool(row.get("is_hidden")) else 0,
                    1 if bool(row.get("is_authority_critical")) else 0,
                    1 if bool(projected.get("graph_ready")) else 0,
                    _text(row.get("source_event_id")),
                    _text(row.get("source_span_id")),
                    _text(row.get("source_quote_hash")),
                    _text(row.get("receipt_id")),
                    _text(row.get("authority_class")),
                    1 if bool(row.get("truth_eligible")) else 0,
                    _text(row.get("support_visibility")),
                    _text(row.get("valid_from")),
                    _text(row.get("valid_to")),
                    _text(row.get("transaction_time")),
                    _text(row.get("superseded_by")),
                    _text(row.get("projection_version")),
                    json.dumps(row, ensure_ascii=True, sort_keys=True),
                    str(projected["issue_json"]),
                    str(projected["counter_json"]),
                    timestamp,
                ),
            )
        self._mark_l0_superseded_events(
            event,
            superseded_by_event_id=event_id,
            projected_at=timestamp,
        )

    @_locked
    def rebuild_current_truth_l0_snapshot(
        self,
        *,
        limit: int = 5000,
        projected_at: str | None = None,
    ) -> dict[str, Any]:
        timestamp = _text(projected_at) or utc_now_iso()
        rows = _canonical_rows_chronological(self.list_canonical_memory_events(limit=max(int(limit or 0), 1)))
        events = [row.get("event") for row in rows if isinstance(row.get("event"), Mapping)]
        self.conn.execute("DELETE FROM current_truth_l0_rows")
        for event in events:
            self._upsert_current_truth_l0_from_event(event, projected_at=timestamp)
        self.conn.commit()
        return self.get_current_truth_l0_snapshot(limit=limit, checked_at=timestamp)

    @_locked
    def _bootstrap_current_truth_l0_if_needed(self) -> None:
        canonical_count = int(
            self.conn.execute("SELECT COUNT(*) AS count FROM canonical_memory_events").fetchone()["count"]
        )
        if canonical_count <= 0:
            return
        snapshot_count = int(
            self.conn.execute("SELECT COUNT(*) AS count FROM current_truth_l0_rows").fetchone()["count"]
        )
        if snapshot_count > 0:
            return
        self.rebuild_current_truth_l0_snapshot(limit=canonical_count)

    def _current_truth_l0_deep_graph_path(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        current_count = 0
        prior_count = 0
        inspect_count = 0
        for item in rows:
            row = item["row"]
            if not item.get("graph_ready") or _text(row.get("memory_kind")) not in _GRAPH_MEMORY_KINDS:
                continue
            reason_codes = {_text(reason) for reason in _list(row.get("projection_reason_codes"))}
            answerable = _ANSWER_SAFE_REASON in reason_codes
            if answerable:
                current_count += 1
            elif _text(row.get("valid_to")) or _text(row.get("superseded_by")):
                prior_count += 1
            else:
                inspect_count += 1
        available = bool(current_count or prior_count or inspect_count)
        return {
            "available": available,
            "graph_projection_schema": "brainstack.graphiti_projection.v1" if available else "brainstack.graphiti_projection.v1",
            "graph_projection_status": "pass",
            "current_edge_count": current_count,
            "prior_edge_count": prior_count,
            "inspect_only_edge_count": inspect_count,
            "temporal_or_conflict_path_available": bool(prior_count or inspect_count),
            "current_truth_view_is_graph_authority": False,
        }

    def _current_truth_l0_view_from_raw_rows(
        self,
        raw_rows: list[Any],
        *,
        checked: str,
        source: str,
    ) -> dict[str, Any]:
        projected_rows: list[dict[str, Any]] = []
        counters = _empty_counters()
        issues: list[dict[str, Any]] = []
        for raw in raw_rows:
            row = _loads_mapping(raw["row_json"])
            counter_json = _loads_mapping(raw["counter_json"])
            for key in _COUNTER_KEYS:
                counters[key] += int(counter_json.get(key) or 0)
            issue = _loads_mapping(raw["issue_json"])
            if issue:
                issues.append(issue)
            projected_rows.append(
                {
                    "row_type": str(raw["row_type"] or ""),
                    "row": row,
                    "projected_at": str(raw["projected_at"] or ""),
                    "graph_ready": bool(raw["graph_ready"]),
                }
            )

        current_rows = sorted(
            [item["row"] for item in projected_rows if item["row_type"] == "current_truth"],
            key=_row_sort_key,
        )
        non_answerable_rows = sorted(
            [item["row"] for item in projected_rows if item["row_type"] == "non_answerable"],
            key=_row_sort_key,
        )
        issues.sort(key=lambda item: _text(item.get("event_id")))
        span_rows = sorted(
            (
                (
                    _text(item["row"].get("transaction_time")),
                    _text(item["row"].get("event_id")),
                    _text(item["row"].get("source_event_id")),
                )
                for item in projected_rows
                if _text(item["row"].get("event_id")) or _text(item["row"].get("source_event_id"))
            )
        )
        if span_rows:
            source_event_ids = sorted({row[2] for row in span_rows if row[2]})
            source_event_span = {
                "source_event_count": len(source_event_ids),
                "first_event_id": span_rows[0][1],
                "last_event_id": span_rows[-1][1],
                "min_transaction_time": span_rows[0][0],
                "max_transaction_time": span_rows[-1][0],
                "source_event_ids": source_event_ids,
            }
        else:
            source_event_span = {
                "source_event_count": 0,
                "first_event_id": "",
                "last_event_id": "",
                "min_transaction_time": "",
                "max_transaction_time": "",
                "source_event_ids": [],
            }
        receipt_ids = {
            _text(item["row"].get("receipt_id"))
            for item in projected_rows
            if bool(item["row"].get("truth_eligible")) and _text(item["row"].get("support_visibility")) == "answer_evidence"
        }
        missing_receipts = sum(
            1
            for item in projected_rows
            if bool(item["row"].get("truth_eligible"))
            and _text(item["row"].get("support_visibility")) == "answer_evidence"
            and not _text(item["row"].get("receipt_id"))
        )
        projected_at_values = sorted({_text(item.get("projected_at")) for item in projected_rows if _text(item.get("projected_at"))})
        rebuilt_at = projected_at_values[-1] if projected_at_values else checked
        view: dict[str, Any] = {
            "schema": CURRENT_TRUTH_VIEW_SCHEMA_VERSION,
            "status": "pass",
            "contract": {
                "rebuildable_from_canonical_events": True,
                "second_write_authority": False,
                "durable_truth_writes": False,
                "admission_receipt_override": False,
                "raw_truth_write_api": False,
                "l0_snapshot_is_projection_only": True,
            },
            "rebuild": {
                "projection_version": CURRENT_TRUTH_VIEW_PROJECTION_VERSION,
                "rebuilt_at": rebuilt_at,
                "checked_at": checked,
                "cache_max_age_seconds": 0,
                "cache_age_seconds": 0,
                "freshness_status": "fresh",
                "freshness_diagnostics_present": True,
                "source": source,
                "ordinary_hot_path_rebuild": False,
            },
            "source_event_span": source_event_span,
            "receipt_coverage": {
                "answer_truth_row_count": sum(
                    1
                    for item in projected_rows
                    if bool(item["row"].get("truth_eligible"))
                    and _text(item["row"].get("support_visibility")) == "answer_evidence"
                ),
                "receipt_count": len({receipt for receipt in receipt_ids if receipt}),
                "missing_receipt_count": missing_receipts,
                "receipt_ids": sorted(receipt for receipt in receipt_ids if receipt),
            },
            "current_truth_rows": current_rows,
            "non_answerable_rows": non_answerable_rows,
            "issues": issues,
            "counters": counters,
            "deep_graph_path": self._current_truth_l0_deep_graph_path(projected_rows),
        }
        public_safety_issues = validate_current_truth_view_public_safety(view)
        counters["raw_text_leak_count"] = len(public_safety_issues)
        view["public_safety"] = {
            "public_safe": not public_safety_issues,
            "issues": public_safety_issues,
        }
        if public_safety_issues or counters["unsafe_answer_truth_projection_count"]:
            view["status"] = "fail"
        snapshot = {
            "schema": view.get("schema"),
            "contract": view.get("contract"),
            "source_event_span": view.get("source_event_span"),
            "receipt_coverage": view.get("receipt_coverage"),
            "current_truth_rows": view.get("current_truth_rows"),
            "non_answerable_rows": view.get("non_answerable_rows"),
            "issues": view.get("issues"),
            "counters": view.get("counters"),
            "deep_graph_path": view.get("deep_graph_path"),
        }
        view["deterministic_snapshot_hash"] = _snapshot_hash(snapshot)
        return view

    def get_current_truth_l0_snapshot(
        self,
        *,
        principal_scope_key: str = "",
        limit: int = 5000,
        checked_at: str | None = None,
    ) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if principal_scope_key:
            clauses.append("principal_scope_key = ?")
            params.append(str(principal_scope_key))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        raw_rows = self.conn.execute(
            f"""
            SELECT row_type, row_json, issue_json, counter_json, projected_at,
                   graph_ready, memory_kind, event_id, source_event_id, transaction_time
            FROM current_truth_l0_rows
            {where}
            ORDER BY principal_scope_key ASC, stable_fact_id ASC, event_id ASC
            LIMIT ?
            """,
            (*params, max(int(limit or 0), 1)),
        ).fetchall()
        checked = _text(checked_at) or utc_now_iso()
        return self._current_truth_l0_view_from_raw_rows(
            list(raw_rows),
            checked=checked,
            source="current_truth_l0_snapshot",
        )

    def get_current_truth_l0_candidates(
        self,
        *,
        principal_scope_key: str = "",
        target_slots: tuple[str, ...] = (),
        stable_fact_ids: tuple[str, ...] = (),
        limit: int = 96,
        checked_at: str | None = None,
    ) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if principal_scope_key:
            clauses.append("principal_scope_key = ?")
            params.append(str(principal_scope_key))

        target_conditions: list[str] = []
        normalized_target_slots = tuple(dict.fromkeys(_text(item) for item in target_slots if _text(item)))
        normalized_fact_ids = tuple(dict.fromkeys(_text(item) for item in stable_fact_ids if _text(item)))
        if normalized_target_slots:
            placeholders = ",".join("?" for _ in normalized_target_slots)
            target_conditions.append(f"target_slot IN ({placeholders})")
            params.extend(normalized_target_slots)
        if normalized_fact_ids:
            placeholders = ",".join("?" for _ in normalized_fact_ids)
            target_conditions.append(f"stable_fact_id IN ({placeholders})")
            params.extend(normalized_fact_ids)
        if target_conditions:
            clauses.append(f"({' OR '.join(target_conditions)})")
        else:
            clauses.append("0 = 1")

        where = f"WHERE {' AND '.join(clauses)}"
        raw_rows = self.conn.execute(
            f"""
            SELECT row_type, row_json, issue_json, counter_json, projected_at,
                   graph_ready, memory_kind, event_id, source_event_id, transaction_time
            FROM current_truth_l0_rows
            {where}
            ORDER BY principal_scope_key ASC, target_slot ASC, stable_fact_id ASC, event_id ASC
            LIMIT ?
            """,
            (*params, max(int(limit or 0), 1)),
        ).fetchall()
        view = self._current_truth_l0_view_from_raw_rows(
            list(raw_rows),
            checked=_text(checked_at) or utc_now_iso(),
            source="current_truth_l0_targeted",
        )
        view["targeted_query"] = {
            "target_slots": list(normalized_target_slots),
            "stable_fact_ids": list(normalized_fact_ids),
            "principal_scope_key": str(principal_scope_key or ""),
            "row_count": len(raw_rows),
        }
        return view

    def compare_current_truth_l0_to_rebuild(
        self,
        *,
        limit: int = 5000,
        checked_at: str | None = None,
    ) -> dict[str, Any]:
        timestamp = _text(checked_at) or utc_now_iso()
        canonical_rows = _canonical_rows_chronological(self.list_canonical_memory_events(limit=max(int(limit or 0), 1)))
        events = [row.get("event") for row in canonical_rows if isinstance(row.get("event"), Mapping)]
        rebuilt = rebuild_current_truth_view(events, rebuilt_at=timestamp, checked_at=timestamp)
        self.rebuild_current_truth_l0_snapshot(limit=limit, projected_at=timestamp)
        snapshot = self.get_current_truth_l0_snapshot(limit=limit, checked_at=timestamp)
        mismatches: list[str] = []
        for key in ("current_truth_rows", "non_answerable_rows", "issues", "counters", "deep_graph_path"):
            if rebuilt.get(key) != snapshot.get(key):
                mismatches.append(key)
        return {
            "schema": "brainstack.current_truth_l0_parity.v1",
            "status": "pass" if not mismatches else "fail",
            "mismatches": mismatches,
            "canonical_event_count": len(events),
            "snapshot_row_count": len(snapshot.get("current_truth_rows") or []) + len(snapshot.get("non_answerable_rows") or []),
            "ordinary_hot_path_rebuild": False,
            "rebuilt_status": rebuilt.get("status"),
            "snapshot_status": snapshot.get("status"),
        }
