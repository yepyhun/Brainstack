from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Set

import kuzu


def _decode_json_object(value: Any) -> Dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _tokens(query: str) -> List[str]:
    seen: Set[str] = set()
    items: List[str] = []
    for token in re.findall(r"[^\W_]+", str(query or "").lower(), flags=re.UNICODE):
        cleaned = token.strip()
        if len(cleaned) < 2 or cleaned in seen:
            continue
        seen.add(cleaned)
        items.append(cleaned)
    return items[:8]


def _coerce_number(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


SCHEMA_QUERIES = """
CREATE NODE TABLE IF NOT EXISTS Entity(
    id INT64,
    canonical_name STRING,
    normalized_name STRING,
    updated_at STRING,
    PRIMARY KEY(id)
);

CREATE NODE TABLE IF NOT EXISTS State(
    id INT64,
    entity_id INT64,
    attribute STRING,
    value_text STRING,
    source STRING,
    metadata_json STRING,
    valid_from STRING,
    valid_to STRING,
    is_current BOOL,
    PRIMARY KEY(id)
);

CREATE NODE TABLE IF NOT EXISTS Conflict(
    id INT64,
    entity_id INT64,
    attribute STRING,
    current_state_id INT64,
    current_value STRING,
    candidate_value STRING,
    candidate_source STRING,
    metadata_json STRING,
    status STRING,
    created_at STRING,
    updated_at STRING,
    PRIMARY KEY(id)
);

CREATE REL TABLE IF NOT EXISTS RELATES_TO(
    FROM Entity TO Entity,
    id INT64,
    predicate STRING,
    source STRING,
    metadata_json STRING,
    created_at STRING,
    active BOOL
);

CREATE REL TABLE IF NOT EXISTS INFERRED_RELATES_TO(
    FROM Entity TO Entity,
    id INT64,
    predicate STRING,
    source STRING,
    metadata_json STRING,
    created_at STRING,
    updated_at STRING,
    active BOOL
);
"""


class KuzuGraphBackend:
    target_name = "graph.kuzu"

    def __init__(self, *, db_path: str) -> None:
        self._db_path = str(db_path)
        self._db: kuzu.Database | None = None
        self._conn: kuzu.Connection | None = None

    @property
    def conn(self) -> kuzu.Connection:
        if self._conn is None:
            raise RuntimeError("KuzuGraphBackend is not open")
        return self._conn

    def _execute(self, query: str, params: Dict[str, Any] | None = None):
        if params is None:
            return self.conn.execute(query)
        return self.conn.execute(query, params)

    def open(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(self._db_path)
        self._conn = kuzu.Connection(self._db)
        self._execute(SCHEMA_QUERIES)

    def close(self) -> None:
        self._conn = None
        self._db = None

    def is_empty(self) -> bool:
        rows = self._execute("MATCH (e:Entity) RETURN count(e) AS count").get_next()
        return int(rows[0] or 0) == 0

    def _ensure_entity(self, entity: Dict[str, Any]) -> None:
        self._execute(
            """
            MERGE (e:Entity {id: $id})
            SET e.canonical_name = $canonical_name,
                e.normalized_name = $normalized_name,
                e.updated_at = $updated_at
            """,
            {
                "id": int(entity["id"]),
                "canonical_name": str(entity["canonical_name"]),
                "normalized_name": str(entity["normalized_name"]),
                "updated_at": str(entity.get("updated_at") or ""),
            },
        )

    def publish_entity_subgraph(self, snapshot: Dict[str, Any]) -> None:
        entity = snapshot["entity"]
        entity_id = int(entity["id"])
        state_ids = [int(state["row_id"]) for state in snapshot.get("states", [])]
        conflict_ids = [int(conflict["row_id"]) for conflict in snapshot.get("conflicts", [])]
        self._execute("BEGIN TRANSACTION")
        try:
            self._ensure_entity(entity)
            if state_ids:
                self._execute(
                    "MATCH (s:State) WHERE s.entity_id = $entity_id AND NOT s.id IN $state_ids DETACH DELETE s",
                    {"entity_id": entity_id, "state_ids": state_ids},
                )
            else:
                self._execute("MATCH (s:State) WHERE s.entity_id = $entity_id DETACH DELETE s", {"entity_id": entity_id})
            if conflict_ids:
                self._execute(
                    "MATCH (c:Conflict) WHERE c.entity_id = $entity_id AND NOT c.id IN $conflict_ids DETACH DELETE c",
                    {"entity_id": entity_id, "conflict_ids": conflict_ids},
                )
            else:
                self._execute("MATCH (c:Conflict) WHERE c.entity_id = $entity_id DETACH DELETE c", {"entity_id": entity_id})
            self._execute("MATCH (e:Entity {id: $entity_id})-[r:RELATES_TO]->(:Entity) DELETE r", {"entity_id": entity_id})
            self._execute(
                "MATCH (e:Entity {id: $entity_id})-[r:INFERRED_RELATES_TO]->(:Entity) DELETE r",
                {"entity_id": entity_id},
            )

            for state in snapshot.get("states", []):
                self._execute(
                """
                MERGE (s:State {id: $id})
                SET s.entity_id = $entity_id,
                    s.attribute = $attribute,
                    s.value_text = $value_text,
                    s.source = $source,
                    s.metadata_json = $metadata_json,
                    s.valid_from = $valid_from,
                    s.valid_to = $valid_to,
                    s.is_current = $is_current
                """,
                {
                    "id": int(state["row_id"]),
                    "entity_id": entity_id,
                    "attribute": str(state["predicate"]),
                    "value_text": str(state["object_value"]),
                    "source": str(state.get("source") or ""),
                    "metadata_json": json.dumps(state.get("metadata") or {}, ensure_ascii=True, sort_keys=True),
                    "valid_from": str(state.get("happened_at") or ""),
                    "valid_to": str(state.get("valid_to") or ""),
                    "is_current": bool(state.get("is_current")),
                },
            )

            for conflict in snapshot.get("conflicts", []):
                self._execute(
                """
                MERGE (c:Conflict {id: $id})
                SET c.entity_id = $entity_id,
                    c.attribute = $attribute,
                    c.current_state_id = $current_state_id,
                    c.current_value = $current_value,
                    c.candidate_value = $candidate_value,
                    c.candidate_source = $candidate_source,
                    c.metadata_json = $metadata_json,
                    c.status = $status,
                    c.created_at = $created_at,
                    c.updated_at = $updated_at
                """,
                {
                    "id": int(conflict["row_id"]),
                    "entity_id": entity_id,
                    "attribute": str(conflict["predicate"]),
                    "current_state_id": int(conflict.get("current_state_id") or 0),
                    "current_value": str(conflict.get("object_value") or ""),
                    "candidate_value": str(conflict.get("conflict_value") or ""),
                    "candidate_source": str(conflict.get("conflict_source") or ""),
                    "metadata_json": json.dumps(conflict.get("conflict_metadata") or {}, ensure_ascii=True, sort_keys=True),
                    "status": "open",
                    "created_at": str(conflict.get("happened_at") or ""),
                    "updated_at": str(conflict.get("happened_at") or ""),
                },
            )

            for relation in snapshot.get("relations", []):
                target = relation["object_entity"]
                self._ensure_entity(target)
                self._execute(
                """
                MATCH (a:Entity {id: $source_id}), (b:Entity {id: $target_id})
                CREATE (a)-[:RELATES_TO {
                    id: $id,
                    predicate: $predicate,
                    source: $source,
                    metadata_json: $metadata_json,
                    created_at: $created_at,
                    active: $active
                }]->(b)
                """,
                {
                    "source_id": entity_id,
                    "target_id": int(target["id"]),
                    "id": int(relation["row_id"]),
                    "predicate": str(relation["predicate"]),
                    "source": str(relation.get("source") or ""),
                    "metadata_json": json.dumps(relation.get("metadata") or {}, ensure_ascii=True, sort_keys=True),
                    "created_at": str(relation.get("happened_at") or ""),
                    "active": bool(relation.get("active", True)),
                },
            )

            for relation in snapshot.get("inferred_relations", []):
                target = relation["object_entity"]
                self._ensure_entity(target)
                self._execute(
                """
                MATCH (a:Entity {id: $source_id}), (b:Entity {id: $target_id})
                CREATE (a)-[:INFERRED_RELATES_TO {
                    id: $id,
                    predicate: $predicate,
                    source: $source,
                    metadata_json: $metadata_json,
                    created_at: $created_at,
                    updated_at: $updated_at,
                    active: $active
                }]->(b)
                """,
                {
                    "source_id": entity_id,
                    "target_id": int(target["id"]),
                    "id": int(relation["row_id"]),
                    "predicate": str(relation["predicate"]),
                    "source": str(relation.get("source") or ""),
                    "metadata_json": json.dumps(relation.get("metadata") or {}, ensure_ascii=True, sort_keys=True),
                    "created_at": str(relation.get("happened_at") or ""),
                    "updated_at": str(relation.get("happened_at") or ""),
                    "active": bool(relation.get("active", True)),
                },
            )
            self._execute("COMMIT")
        except Exception:
            try:
                self._execute("ROLLBACK")
            except Exception:
                pass
            raise

    def _seed_entity_ids(self, query: str, *, limit: int) -> List[int]:
        tokens = _tokens(query)
        if not tokens:
            return []
        ids: List[int] = []
        seen: Set[int] = set()

        def add_rows(rows: Iterable[List[Any]]) -> None:
            for row in rows:
                entity_id = int(row[0])
                if entity_id in seen:
                    continue
                seen.add(entity_id)
                ids.append(entity_id)
                if len(ids) >= limit:
                    return

        for token in tokens:
            if len(ids) >= limit:
                break
            rows = self.conn.execute(
                """
                MATCH (e:Entity)
                WHERE lower(e.canonical_name) CONTAINS lower($term)
                   OR lower(e.normalized_name) CONTAINS lower($term)
                   OR lower($term) CONTAINS lower(e.canonical_name)
                   OR lower($term) CONTAINS lower(e.normalized_name)
                RETURN e.id
                LIMIT $limit
                """,
                {"term": token, "limit": limit},
            )
            collected: List[List[Any]] = []
            while rows.has_next():
                collected.append(rows.get_next())
            add_rows(collected)

        for token in tokens:
            if len(ids) >= limit:
                break
            rows = self.conn.execute(
                """
                MATCH (s:State)
                WHERE lower(s.attribute) CONTAINS lower($term)
                   OR lower(s.value_text) CONTAINS lower($term)
                RETURN s.entity_id
                LIMIT $limit
                """,
                {"term": token, "limit": limit},
            )
            collected = []
            while rows.has_next():
                collected.append(rows.get_next())
            add_rows(collected)

        for token in tokens:
            if len(ids) >= limit:
                break
            rows = self.conn.execute(
                """
                MATCH (c:Conflict)
                WHERE c.status = 'open'
                  AND (
                    lower(c.attribute) CONTAINS lower($term)
                    OR lower(c.current_value) CONTAINS lower($term)
                    OR lower(c.candidate_value) CONTAINS lower($term)
                  )
                RETURN c.entity_id
                LIMIT $limit
                """,
                {"term": token, "limit": limit},
            )
            collected = []
            while rows.has_next():
                collected.append(rows.get_next())
            add_rows(collected)

        for token in tokens:
            if len(ids) >= limit:
                break
            rows = self.conn.execute(
                """
                MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
                WHERE lower(a.canonical_name) CONTAINS lower($term)
                   OR lower(b.canonical_name) CONTAINS lower($term)
                   OR lower($term) CONTAINS lower(a.canonical_name)
                   OR lower($term) CONTAINS lower(b.canonical_name)
                   OR lower(r.predicate) CONTAINS lower($term)
                RETURN a.id, b.id
                LIMIT $limit
                """,
                {"term": token, "limit": limit},
            )
            collected = []
            while rows.has_next():
                row = rows.get_next()
                collected.append([row[0]])
                collected.append([row[1]])
            add_rows(collected)

        return ids[:limit]

    def _related_entity_ids(self, seed_ids: List[int], *, limit: int) -> List[int]:
        if not seed_ids:
            return []
        output: List[int] = []
        seen = set(seed_ids)
        patterns = (
            "MATCH (a:Entity)-[:RELATES_TO*1..2]->(b:Entity) WHERE a.id IN $ids RETURN DISTINCT b.id LIMIT $limit",
            "MATCH (a:Entity)<-[:RELATES_TO*1..2]-(b:Entity) WHERE a.id IN $ids RETURN DISTINCT b.id LIMIT $limit",
            "MATCH (a:Entity)-[:INFERRED_RELATES_TO*1..2]->(b:Entity) WHERE a.id IN $ids RETURN DISTINCT b.id LIMIT $limit",
            "MATCH (a:Entity)<-[:INFERRED_RELATES_TO*1..2]-(b:Entity) WHERE a.id IN $ids RETURN DISTINCT b.id LIMIT $limit",
        )
        for query in patterns:
            if len(output) >= limit:
                break
            rows = self.conn.execute(query, {"ids": seed_ids, "limit": limit})
            while rows.has_next():
                entity_id = int(rows.get_next()[0])
                if entity_id in seen:
                    continue
                seen.add(entity_id)
                output.append(entity_id)
                if len(output) >= limit:
                    break
        return output

    def _entity_names(self, entity_ids: List[int]) -> Dict[int, str]:
        if not entity_ids:
            return {}
        rows = self.conn.execute(
            "MATCH (e:Entity) WHERE e.id IN $ids RETURN e.id, e.canonical_name",
            {"ids": entity_ids},
        )
        names: Dict[int, str] = {}
        while rows.has_next():
            row = rows.get_next()
            names[int(row[0])] = str(row[1] or "")
        return names

    def search_graph(self, *, query: str, limit: int) -> List[Dict[str, Any]]:
        seed_ids = self._seed_entity_ids(query, limit=max(limit * 3, 8))
        related_ids = self._related_entity_ids(seed_ids, limit=max(limit * 3, 8))
        all_ids = list(dict.fromkeys(seed_ids + related_ids))
        if not all_ids:
            return []
        entity_names = self._entity_names(all_ids)
        rows: List[Dict[str, Any]] = []

        state_rows = self.conn.execute(
            """
            MATCH (s:State)
            WHERE s.entity_id IN $ids
            RETURN s.id, s.entity_id, s.attribute, s.value_text, s.source, s.metadata_json, s.valid_from, s.valid_to, s.is_current
            LIMIT $limit
            """,
            {"ids": all_ids, "limit": max(limit * 10, 40)},
        )
        while state_rows.has_next():
            row = state_rows.get_next()
            entity_id = int(row[1])
            rows.append(
                {
                    "row_type": "state",
                    "row_id": int(row[0]),
                    "subject": entity_names.get(entity_id, ""),
                    "predicate": str(row[2] or ""),
                    "object_value": str(row[3] or ""),
                    "is_current": bool(row[8]),
                    "happened_at": str(row[6] or ""),
                    "valid_to": str(row[7] or ""),
                    "source": str(row[4] or ""),
                    "metadata": _decode_json_object(row[5]),
                    "conflict_metadata": {},
                    "conflict_source": "",
                    "conflict_value": "",
                    "active": True,
                }
            )

        conflict_rows = self.conn.execute(
            """
            MATCH (c:Conflict)
            WHERE c.entity_id IN $ids AND c.status = 'open'
            RETURN c.id, c.entity_id, c.attribute, c.current_value, c.candidate_value, c.candidate_source, c.metadata_json, c.updated_at
            LIMIT $limit
            """,
            {"ids": all_ids, "limit": max(limit * 6, 24)},
        )
        while conflict_rows.has_next():
            row = conflict_rows.get_next()
            entity_id = int(row[1])
            rows.append(
                {
                    "row_type": "conflict",
                    "row_id": int(row[0]),
                    "subject": entity_names.get(entity_id, ""),
                    "predicate": str(row[2] or ""),
                    "object_value": str(row[3] or ""),
                    "is_current": True,
                    "happened_at": str(row[7] or ""),
                    "valid_to": "",
                    "source": "",
                    "metadata": {},
                    "conflict_metadata": _decode_json_object(row[6]),
                    "conflict_source": str(row[5] or ""),
                    "conflict_value": str(row[4] or ""),
                    "active": True,
                }
            )

        relation_buffer: List[List[Any]] = []
        relation_rows = self.conn.execute(
            """
            MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
            WHERE (a.id IN $ids OR b.id IN $ids) AND r.active = true
            RETURN r.id, a.id, b.id, r.predicate, r.source, r.metadata_json, r.created_at, r.active
            LIMIT $limit
            """,
            {"ids": all_ids, "limit": max(limit * 8, 32)},
        )
        while relation_rows.has_next():
            relation_buffer.append(relation_rows.get_next())

        inferred_buffer: List[List[Any]] = []
        inferred_rows = self.conn.execute(
            """
            MATCH (a:Entity)-[r:INFERRED_RELATES_TO]->(b:Entity)
            WHERE (a.id IN $ids OR b.id IN $ids) AND r.active = true
            RETURN r.id, a.id, b.id, r.predicate, r.source, r.metadata_json, r.updated_at, r.active
            LIMIT $limit
            """,
            {"ids": all_ids, "limit": max(limit * 8, 32)},
        )
        while inferred_rows.has_next():
            inferred_buffer.append(inferred_rows.get_next())

        relation_entity_ids = all_ids[:]
        for row in relation_buffer + inferred_buffer:
            relation_entity_ids.append(int(row[1]))
            relation_entity_ids.append(int(row[2]))
        entity_names.update(self._entity_names(relation_entity_ids))

        for row in relation_buffer:
            rows.append(
                {
                    "row_type": "relation",
                    "row_id": int(row[0]),
                    "subject": entity_names.get(int(row[1]), ""),
                    "predicate": str(row[3] or ""),
                    "object_value": entity_names.get(int(row[2]), ""),
                    "is_current": True,
                    "happened_at": str(row[6] or ""),
                    "valid_to": "",
                    "source": str(row[4] or ""),
                    "metadata": _decode_json_object(row[5]),
                    "conflict_metadata": {},
                    "conflict_source": "",
                    "conflict_value": "",
                    "active": bool(row[7]),
                }
            )

        for row in inferred_buffer:
            rows.append(
                {
                    "row_type": "inferred_relation",
                    "row_id": int(row[0]),
                    "subject": entity_names.get(int(row[1]), ""),
                    "predicate": str(row[3] or ""),
                    "object_value": entity_names.get(int(row[2]), ""),
                    "is_current": True,
                    "happened_at": str(row[6] or ""),
                    "valid_to": "",
                    "source": str(row[4] or ""),
                    "metadata": _decode_json_object(row[5]),
                    "conflict_metadata": {},
                    "conflict_source": "",
                    "conflict_value": "",
                    "active": bool(row[7]),
                }
            )

        return rows

    def list_graph_conflicts(self, *, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            MATCH (c:Conflict)
            WHERE c.status = 'open'
            RETURN c.id, c.entity_id, c.attribute, c.current_value, c.candidate_value, c.status, c.updated_at, c.metadata_json
            ORDER BY c.updated_at DESC
            LIMIT $limit
            """,
            {"limit": limit},
        )
        entity_ids: List[int] = []
        buffer: List[List[Any]] = []
        while rows.has_next():
            row = rows.get_next()
            buffer.append(row)
            entity_ids.append(int(row[1]))
        names = self._entity_names(entity_ids)
        return [
            {
                "id": int(row[0]),
                "entity_name": names.get(int(row[1]), ""),
                "attribute": str(row[2] or ""),
                "current_value": str(row[3] or ""),
                "candidate_value_text": str(row[4] or ""),
                "status": str(row[5] or ""),
                "updated_at": str(row[6] or ""),
                "metadata": _decode_json_object(row[7]),
            }
            for row in buffer
        ]

    def query_typed_metric_sum(
        self,
        *,
        owner_subject: str | None,
        entity_type: str | None,
        entity_type_contains: List[str] | None = None,
        entity_type_excludes: List[str] | None = None,
        metric_attribute: str,
        limit: int,
    ) -> Dict[str, Any] | None:
        rows = self.conn.execute(
            """
            MATCH (e:Entity), (type_state:State), (owner_state:State), (metric_state:State)
            WHERE type_state.entity_id = e.id
              AND type_state.attribute = 'entity_type'
              AND type_state.is_current = true
              AND owner_state.entity_id = e.id
              AND owner_state.attribute = 'owner_subject'
              AND owner_state.is_current = true
              AND metric_state.entity_id = e.id
              AND metric_state.attribute = $metric_attribute
              AND metric_state.is_current = true
            RETURN e.id, e.canonical_name, type_state.value_text, owner_state.value_text, metric_state.value_text, metric_state.valid_from, metric_state.metadata_json
            LIMIT $limit
            """,
            {
                "metric_attribute": metric_attribute,
                "limit": max(8, int(limit) * 8),
            },
        )
        owner_filter = str(owner_subject or "").strip().lower()
        exact_entity_type = str(entity_type or "").strip().lower()
        include_terms = [str(item or "").strip().lower() for item in (entity_type_contains or []) if str(item or "").strip()]
        exclude_terms = [str(item or "").strip().lower() for item in (entity_type_excludes or []) if str(item or "").strip()]
        matches: List[Dict[str, Any]] = []
        total = 0.0
        seen_entity_ids: Set[int] = set()
        while rows.has_next():
            row = rows.get_next()
            entity_id = int(row[0])
            if entity_id in seen_entity_ids:
                continue
            entity_type_value = str(row[2] or "").strip()
            owner_value = str(row[3] or "").strip()
            entity_type_normalized = entity_type_value.lower()
            owner_normalized = owner_value.lower()
            if owner_filter and owner_normalized != owner_filter:
                continue
            if exact_entity_type and entity_type_normalized != exact_entity_type:
                continue
            if include_terms and not any(term in entity_type_normalized for term in include_terms):
                continue
            if exclude_terms and any(term in entity_type_normalized for term in exclude_terms):
                continue
            numeric_value = _coerce_number(row[4])
            if numeric_value is None:
                continue
            seen_entity_ids.add(entity_id)
            total += numeric_value
            matches.append(
                {
                    "entity_id": entity_id,
                    "entity_name": str(row[1] or ""),
                    "entity_type": entity_type_value,
                    "owner_subject": owner_value,
                    "metric_value": numeric_value,
                    "valid_from": str(row[5] or ""),
                    "metadata": _decode_json_object(row[6]),
                }
            )
        if not matches:
            return None
        return {
            "owner_subject": owner_subject,
            "entity_type": entity_type,
            "entity_type_contains": include_terms,
            "entity_type_excludes": exclude_terms,
            "metric_attribute": metric_attribute,
            "count": len(matches),
            "total": total,
            "matches": matches,
        }
