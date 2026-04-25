from __future__ import annotations

import sqlite3


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS continuity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_continuity_session_created
ON continuity_events(session_id, created_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS continuity_fts USING fts5(
    content,
    session_id UNINDEXED,
    kind UNINDEXED,
    tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS transcript_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transcript_session_created
ON transcript_entries(session_id, created_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(
    content,
    session_id UNINDEXED,
    kind UNINDEXED,
    tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS continuity_lifecycle_state (
    session_id TEXT PRIMARY KEY,
    current_frontier_turn_number INTEGER NOT NULL DEFAULT 0,
    last_snapshot_kind TEXT NOT NULL DEFAULT '',
    last_snapshot_turn_number INTEGER NOT NULL DEFAULT 0,
    last_snapshot_message_count INTEGER NOT NULL DEFAULT 0,
    last_snapshot_input_count INTEGER NOT NULL DEFAULT 0,
    last_snapshot_digest TEXT NOT NULL DEFAULT '',
    last_snapshot_at TEXT NOT NULL DEFAULT '',
    last_finalized_turn_number INTEGER NOT NULL DEFAULT 0,
    last_finalized_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_continuity_lifecycle_updated
ON continuity_lifecycle_state(updated_at DESC);

CREATE TABLE IF NOT EXISTS profile_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stable_key TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_profile_category_updated
ON profile_items(category, updated_at DESC);

CREATE TABLE IF NOT EXISTS behavior_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    storage_key TEXT NOT NULL UNIQUE,
    principal_scope_key TEXT NOT NULL DEFAULT '',
    stable_key TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    source_contract_hash TEXT NOT NULL DEFAULT '',
    revision_number INTEGER NOT NULL DEFAULT 1,
    parent_revision_id INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    committed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_behavior_contract_active_scope
ON behavior_contracts(principal_scope_key, stable_key)
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_behavior_contract_scope_revision
ON behavior_contracts(principal_scope_key, stable_key, revision_number DESC, id DESC);

CREATE TABLE IF NOT EXISTS compiled_behavior_policies (
    principal_scope_key TEXT PRIMARY KEY,
    source_storage_key TEXT NOT NULL DEFAULT '',
    source_contract_hash TEXT NOT NULL DEFAULT '',
    source_contract_updated_at TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    compiler_version TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    policy_json TEXT NOT NULL DEFAULT '{}',
    projection_text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stable_key TEXT NOT NULL UNIQUE,
    principal_scope_key TEXT NOT NULL DEFAULT '',
    item_type TEXT NOT NULL DEFAULT 'task',
    title TEXT NOT NULL,
    due_date TEXT NOT NULL DEFAULT '',
    date_scope TEXT NOT NULL DEFAULT 'none',
    optional INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    owner TEXT NOT NULL DEFAULT 'brainstack.task_memory',
    source TEXT NOT NULL,
    source_session_id TEXT NOT NULL DEFAULT '',
    source_turn_number INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_items_scope_due_status
ON task_items(principal_scope_key, due_date, status, optional, updated_at DESC);

CREATE TABLE IF NOT EXISTS operating_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stable_key TEXT NOT NULL UNIQUE,
    principal_scope_key TEXT NOT NULL DEFAULT '',
    record_type TEXT NOT NULL,
    content TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT 'brainstack.operating_truth',
    source TEXT NOT NULL,
    source_session_id TEXT NOT NULL DEFAULT '',
    source_turn_number INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operating_records_scope_type_updated
ON operating_records(principal_scope_key, record_type, updated_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS profile_fts USING fts5(
    content,
    category UNINDEXED,
    stable_key UNINDEXED,
    tokenize = 'unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS operating_fts USING fts5(
    content,
    record_type UNINDEXED,
    stable_key UNINDEXED,
    tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS graph_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_entity_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias_name TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    target_entity_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(normalized_alias, target_entity_id),
    FOREIGN KEY(target_entity_id) REFERENCES graph_entities(id)
);

CREATE INDEX IF NOT EXISTS idx_graph_entity_aliases_normalized
ON graph_entity_aliases(normalized_alias);

CREATE INDEX IF NOT EXISTS idx_graph_entity_aliases_target
ON graph_entity_aliases(target_entity_id);

CREATE TABLE IF NOT EXISTS graph_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_entity_id INTEGER NOT NULL,
    predicate TEXT NOT NULL,
    object_entity_id INTEGER,
    object_text TEXT,
    source TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(subject_entity_id) REFERENCES graph_entities(id),
    FOREIGN KEY(object_entity_id) REFERENCES graph_entities(id)
);

CREATE INDEX IF NOT EXISTS idx_graph_relations_subject
ON graph_relations(subject_entity_id, predicate, created_at DESC);

CREATE TABLE IF NOT EXISTS graph_inferred_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_entity_id INTEGER NOT NULL,
    predicate TEXT NOT NULL,
    object_entity_id INTEGER,
    object_text TEXT,
    source TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(subject_entity_id) REFERENCES graph_entities(id),
    FOREIGN KEY(object_entity_id) REFERENCES graph_entities(id)
);

CREATE INDEX IF NOT EXISTS idx_graph_inferred_relations_subject
ON graph_inferred_relations(subject_entity_id, predicate, updated_at DESC);

CREATE TABLE IF NOT EXISTS graph_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL,
    attribute TEXT NOT NULL,
    value_text TEXT NOT NULL,
    source TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    is_current INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(entity_id) REFERENCES graph_entities(id)
);

CREATE INDEX IF NOT EXISTS idx_graph_states_entity_attribute
ON graph_states(entity_id, attribute, is_current, valid_from DESC);

CREATE TABLE IF NOT EXISTS graph_supersessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prior_state_id INTEGER NOT NULL,
    new_state_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(prior_state_id) REFERENCES graph_states(id),
    FOREIGN KEY(new_state_id) REFERENCES graph_states(id)
);

CREATE TABLE IF NOT EXISTS graph_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL,
    attribute TEXT NOT NULL,
    current_state_id INTEGER NOT NULL,
    candidate_value_text TEXT NOT NULL,
    candidate_source TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(entity_id) REFERENCES graph_entities(id),
    FOREIGN KEY(current_state_id) REFERENCES graph_states(id)
);

CREATE INDEX IF NOT EXISTS idx_graph_conflicts_entity
ON graph_conflicts(entity_id, attribute, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS publish_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_name TEXT NOT NULL,
    object_kind TEXT NOT NULL,
    object_key TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE(target_name, object_kind, object_key)
);

CREATE INDEX IF NOT EXISTS idx_publish_journal_target_status
ON publish_journal(target_name, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS corpus_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stable_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    doc_kind TEXT NOT NULL DEFAULT 'document',
    source TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_corpus_documents_kind_updated
ON corpus_documents(doc_kind, updated_at DESC);

CREATE TABLE IF NOT EXISTS corpus_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    section_index INTEGER NOT NULL,
    heading TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    token_estimate INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES corpus_documents(id) ON DELETE CASCADE,
    UNIQUE(document_id, section_index)
);

CREATE INDEX IF NOT EXISTS idx_corpus_sections_document
ON corpus_sections(document_id, section_index);

CREATE VIRTUAL TABLE IF NOT EXISTS corpus_section_fts USING fts5(
    title,
    heading,
    content,
    document_id UNINDEXED,
    section_index UNINDEXED,
    tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS semantic_evidence_index (
    evidence_key TEXT PRIMARY KEY,
    shelf TEXT NOT NULL,
    row_id INTEGER NOT NULL DEFAULT 0,
    stable_key TEXT NOT NULL DEFAULT '',
    principal_scope_key TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    authority_class TEXT NOT NULL DEFAULT '',
    provenance_class TEXT NOT NULL DEFAULT '',
    content_excerpt TEXT NOT NULL DEFAULT '',
    normalized_text TEXT NOT NULL DEFAULT '',
    terms_json TEXT NOT NULL DEFAULT '[]',
    source_updated_at TEXT NOT NULL DEFAULT '',
    fingerprint TEXT NOT NULL DEFAULT '',
    index_version TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_semantic_evidence_scope_shelf
ON semantic_evidence_index(principal_scope_key, shelf, active, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_semantic_evidence_fingerprint
ON semantic_evidence_index(fingerprint, index_version, active);

CREATE TABLE IF NOT EXISTS tier2_run_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL DEFAULT '',
    turn_number INTEGER NOT NULL DEFAULT 0,
    trigger_reason TEXT NOT NULL DEFAULT '',
    request_status TEXT NOT NULL DEFAULT 'unknown',
    parse_status TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL DEFAULT 'unknown',
    transcript_count INTEGER NOT NULL DEFAULT 0,
    extracted_counts_json TEXT NOT NULL DEFAULT '{}',
    action_counts_json TEXT NOT NULL DEFAULT '{}',
    writes_performed INTEGER NOT NULL DEFAULT 0,
    no_op_reasons_json TEXT NOT NULL DEFAULT '[]',
    error_reason TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tier2_run_records_session_updated
ON tier2_run_records(session_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS applied_migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()

