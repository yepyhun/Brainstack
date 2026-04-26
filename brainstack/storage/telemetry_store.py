from __future__ import annotations

from .store_protocol import StoreRuntimeBase
from .store_runtime import (
    Any,
    Dict,
    Iterable,
    _decode_json_object,
    _locked,
    apply_retrieval_telemetry,
    json,
    utc_now_iso,
)

class TelemetryStoreMixin(StoreRuntimeBase):
    @_locked
    def record_graph_retrievals(self, *, rows: Iterable[Dict[str, Any]]) -> int:
        updated = 0
        now = utc_now_iso()
        table_by_type = {
            "state": "graph_states",
            "relation": "graph_relations",
            "conflict": "graph_conflicts",
            "inferred_relation": "graph_inferred_relations",
        }
        for row in rows:
            row_type = str(row.get("row_type") or "").strip()
            row_id = int(row.get("row_id") or 0)
            table = table_by_type.get(row_type)
            if not table or row_id <= 0:
                continue
            existing = self.conn.execute(
                f"SELECT metadata_json FROM {table} WHERE id = ?",
                (row_id,),
            ).fetchone()
            if not existing:
                continue
            metadata = _decode_json_object(existing["metadata_json"])
            metadata = apply_retrieval_telemetry(
                metadata,
                matched=True,
                fallback=False,
                served_at=now,
            )
            self.conn.execute(
                f"UPDATE {table} SET metadata_json = ?{', updated_at = ?' if table == 'graph_conflicts' else ''} WHERE id = ?",
                ((json.dumps(metadata, ensure_ascii=True, sort_keys=True), now, row_id) if table == "graph_conflicts" else (json.dumps(metadata, ensure_ascii=True, sort_keys=True), row_id)),
            )
            updated += 1
        if updated:
            self.conn.commit()
        return updated

    @_locked
    def record_corpus_retrievals(self, *, rows: Iterable[Dict[str, Any]]) -> int:
        updated = 0
        now = utc_now_iso()
        for row in rows:
            section_id = int(row.get("section_id") or 0)
            if section_id <= 0:
                continue
            existing = self.conn.execute(
                "SELECT metadata_json FROM corpus_sections WHERE id = ?",
                (section_id,),
            ).fetchone()
            if not existing:
                continue
            metadata = _decode_json_object(existing["metadata_json"])
            metadata = apply_retrieval_telemetry(
                metadata,
                matched=True,
                fallback=False,
                served_at=now,
            )
            self.conn.execute(
                "UPDATE corpus_sections SET metadata_json = ? WHERE id = ?",
                (json.dumps(metadata, ensure_ascii=True, sort_keys=True), section_id),
            )
            updated += 1
        if updated:
            self.conn.commit()
        return updated
