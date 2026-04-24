# Phase 60 Architecture Decision

## Purpose

Freeze the minimal, Brainstack-owned correction shape before implementation so Phase 60 does not drift into Hermes-general cleanup, user-specific rescue logic, or heuristic sprawl.

## Decision 1: Temporal Grounding

### Chosen mechanism

Use **structured-lane-first temporal authority**.

- `task_memory` and `operating_truth` remain the first-class owner-backed lanes for task-like and operating-like recall.
- For task-like lookups, Brainstack must prefer committed open task records and must not let transcript/continuity fallback masquerade as present or upcoming task truth.
- We will not add a generic transcript-wide reminder detector or keyword farm.

### Why

- Brainstack already has real `task_memory` and `operating_truth` structures.
- The observed stale reminder problem becomes dangerous when unstructured transcript/continuity evidence is allowed to compete with structured task truth.
- A schema-light routing/ranking correction is lower risk than a broad new temporal classification layer.

### Explicit non-decisions

- No new global reminder lane.
- No regex/keyword list for "reminder-like" sentences.
- No broad host scheduler lookup on every Brainstack retrieval path.

## Decision 2: Provenance and Trust

### Chosen mechanism

Reduce durable contamination at the **Tier-2 transcript ingestion boundary** by making Tier-2 extraction consume **user-authored evidence only** from merged turn transcript rows.

- Transcript rows may remain stored as combined `User:` / `Assistant:` records for continuity and debugging.
- Tier-2 durable extraction must not treat the assistant half of those combined rows as equal-authority evidence.
- This removes the current path where assistant self-diagnosis, speculative operational narrative, and stale assistant reminder text can be promoted into continuity, decisions, and temporal events.

### Why

- Session-end durable admission already excludes non-user roles.
- The real contamination path is merged turn transcript batching for Tier-2 extraction.
- User-only Tier-2 evidence is a provenance-first fix, not a heuristic detector.

### Explicit non-decisions

- No locale-specific classifier for "assistant self-diagnosis".
- No keyword blacklist for phrases like "I fixed" or "I diagnosed".
- No attempt to preserve assistant-authored durable truth inside Tier-2 during this phase.

## Decision 3: Reflection-Path Handling

### Chosen mechanism

Add the **thinnest possible host seam** for explicit built-in memory write origin metadata, then let Brainstack fail closed on reflection-generated writes.

- Extend the memory-write bridge to optionally pass metadata, including `write_origin`.
- Tag background review writes as `background_review`.
- Brainstack `on_memory_write(...)` may then refuse to mirror those writes into authoritative Brainstack durable state.

### Why

- Without explicit origin metadata, Brainstack cannot distinguish ordinary explicit user memory writes from background reflection-generated memory writes.
- Stopping all native memory mirroring would break valid explicit-memory behavior.
- A small write-origin seam is justified because the Brainstack universal contract cannot be preserved safely without it.

### Explicit non-decisions

- No broad reflection system rewrite.
- No generic host cleanup beyond write-origin metadata propagation.
- No attempt to redesign Hermes background review behavior in Phase 60.

## Scope Guard

These decisions authorize only:

- Brainstack transcript/extraction changes
- Brainstack retrieval/routing changes tied to structured task authority
- The minimal memory-write origin seam required for Brainstack correctness
- Live-state cleanup only where contaminated Brainstack state would otherwise invalidate proof

These decisions do **not** authorize:

- Generic Hermes cron fixes
- Generic Discord UX cleanup
- Provider/runtime fallback cleanup
- Case-study-specific rescue logic for Tomi, Hungarian wording, or one thread

## Success Shape

Phase 60 is correct only if:

- stale task/reminder text can no longer outrank structured current task truth in Brainstack-owned recall paths
- assistant-authored transcript narrative no longer becomes durable Brainstack continuity/decision/temporal truth through Tier-2 extraction
- reflection-generated explicit memory writes no longer silently enter Brainstack as ordinary user-established truth
- the implementation remains narrow, explainable, and free of keyword farms
