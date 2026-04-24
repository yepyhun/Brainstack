# Phase 18 Context

## Discuss Outcome

Phase 18 no longer needs another architecture debate.

The accepted recovery direction is already fixed:

- Brainstack stays the thin shell
- L1 has already been recentered around donor-first executive retrieval
- L2 now has to restore real Graphiti-shaped graph power
- the default embedded graph target is `Kuzu`
- the project must not slide back to SQLite-only graph behavior if that weakens graph usefulness

This phase exists because Phase 16 made L2 safer and cleaner, but not yet donor-strong enough.
It is also the first recovery phase where a second active storage motor must become real beside the shell state store.

## What “Graphiti-Recentered L2” Means

For Phase `18`, the primary L2 behavior must be:

- stronger relationship discovery
- materially better multi-hop graph usefulness
- real temporal truth handling
- clearer separation between:
  - explicit current truth
  - historical truth
  - conflicts
  - inferred links

The target is not “nicer graph packaging”.
The target is a graph that is genuinely more useful in live recall and reasoning.

## Current Local Debt That Phase 18 Must Address

The current Brainstack L2 still carries too much local approximation:

- `brainstack/graph.py` still performs local regex-shaped graph candidate extraction
- `brainstack/db.py` still owns the active graph storage and search path
- `brainstack/reconciler.py` still has to compensate for limited graph power downstream
- `brainstack/donors/graph_adapter.py` is still only a thin pass-through into local graph ingestion

These were acceptable as bounded earlier phases.
They are not acceptable as the claimed final L2 shape.

## Brainstack Job vs Donor Job

### Brainstack job

- own cross-store ingest consistency
- keep non-blocking provider behavior
- own deterministic publish / retry / partial-failure handling
- keep user-facing packaging and host boundaries stable
- keep deterministic reconciliation where it is truly shell work rather than hidden graph intelligence

### Donor job

- provide the real graph intelligence
- provide strong relationship traversal and graph retrieval
- carry temporal truth usefulness in substance, not only in storage shape
- make the L1 graph channel materially stronger without requiring another L1 redesign

## Hard Constraints Already Accepted

- `Kuzu` is the default L2 embedded backend target
- this phase must not reopen the all-SQLite memory-engine idea
- this phase must not turn into a service zoo
- this phase must not hide graph weakness behind nicer packaging
- this phase must not solve graph weakness with shallow local hacks
- live rebuild is not a routine execution requirement; use it only for bounded runtime proof if needed

## Ingest / Consistency Constraint

Large-corpus recovery implies many L2 extraction and graph-write operations.

That means Phase `18` must plan for:

- the first concrete cross-store ingest journal implementation between shell state and `Kuzu`
- resumable graph ingest
- idempotent graph publication
- partial-failure visibility between shell state and graph backend state
- retry without duplicating graph truth

This is not a new subsystem.
It is part of the Brainstack shell’s accepted cross-store consistency responsibility.
It must not be deferred to `19`, because `19` adds a third motor and should extend this mechanism rather than invent it late.

## High Acceptance Bar

Phase `18` is only successful if the result is strong enough that calling it “Graphiti-recentered” is defensible.

That means:

- better graph usefulness in real conversations
- better retrieval of connected prior facts
- better temporal and relational usefulness
- no fallback to cosmetic wins dressed up as graph restoration

## Recommended Effort

`xhigh`
