# Phase 74 Procedure/Session Memory Contract

## Decision

Brainstack may store and recall procedure/session knowledge only as typed operating read-model records.

This phase adds two operating record types:

- `procedure_memory`: durable "how this work is normally done" memory.
- `session_state`: bounded current-session or handoff state with explicit temporal validity.

Both record types remain evidence. They do not execute, schedule, approve, message, or govern runtime behavior.

## Authority Boundary

Brainstack-owned:

- typed storage for `procedure_memory` and `session_state`
- principal-scoped recall through operating evidence
- inspect/retrieval visibility with evidence ids
- expiry filtering for temporally bounded session records

Runtime-owned:

- session-start ordering
- scheduler or cron behavior
- task execution
- approval enforcement
- user messaging

## Temporal Rule

`session_state` records with expired `metadata.temporal.valid_to` must not be surfaced as current operating truth.

Expiry applies to:

- operating list recall
- operating keyword recall
- semantic evidence materialization
- local typed operating probe fallback

The read path may return an active `session_state` only when the query has enough typed lexical/semantic relevance. A single overlapping common term must not promote an unrelated active session record into user-facing truth.

## Non-Goals

- No scheduler tool.
- No executor tool.
- No approval tool.
- No duplicate skill system.
- No workflow ownership inside Brainstack.
- No locale-specific cue lists or phrase farms.

