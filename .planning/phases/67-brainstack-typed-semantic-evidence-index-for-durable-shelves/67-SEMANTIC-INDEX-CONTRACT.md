# Phase 67 Semantic Evidence Index Contract

## Contract

The semantic evidence index is a derived index over authoritative Brainstack rows. It is not durable truth.

Each indexed document stores:

- `evidence_key`
- source `shelf`
- source row ID and stable key
- principal scope
- source/provenance/authority class
- bounded content excerpt
- deterministic normalized terms
- source timestamp
- index fingerprint and index version

## Source Of Truth

Authoritative rows remain in their original shelves:

- profile
- task
- operating
- corpus
- graph state
- continuity

The index search resolves hits back to the current authoritative row before returning retrieval candidates. Stale fingerprints are visible and are not searched.

## No-Heuristic Boundary

The implementation does not add query cue lists, locale dictionaries, prompt classifiers, or renamed keyword routes. It uses deterministic local normalization plus explicit typed `semantic_terms` metadata when the source row provides it.

## Lifecycle

- Backfill: `BrainstackStore.rebuild_semantic_evidence_index(...)`.
- Write refresh: profile/task/operating/corpus/graph/continuity writes refresh their derived shelf slice.
- Drift: `semantic_evidence_channel_status()` reports stale rows and search excludes stale fingerprints.
- Inspect: Phase 65 query inspect sees semantic evidence through retrieval channels and selected evidence.
