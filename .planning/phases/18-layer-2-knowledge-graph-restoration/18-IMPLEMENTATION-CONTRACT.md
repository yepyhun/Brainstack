# Phase 18 Implementation Contract

## Purpose

This document turns the Phase 18 plan into a concrete execution contract.

The goal is to prevent two failure modes:

- a “nice-looking” L2 refactor that keeps the old SQLite graph center alive
- an overgrown rewrite that drags L1 and L3 into the phase and loses control

## Required Workstreams

### Workstream A. Active L2 backend seam

Required output:

- an explicit graph backend interface that is strong enough to host:
  - entity/state writes
  - explicit relation writes
  - inferred relation writes
  - conflict lookup / surfacing
  - graph search / traversal reads
- a `Kuzu`-default implementation path behind that seam

Hard rule:

- the seam must become the active graph center
- it may not exist merely as an unused adapter beside the old SQLite graph path

### Workstream B. SQLite -> Kuzu bootstrap and migration

Required output:

- a repeatable bootstrap path from current local graph state into `Kuzu`
- clear distinction between:
  - initial migration/bootstrap
  - ongoing incremental publish
- fail-closed behavior if bootstrap is incomplete or inconsistent

Hard rule:

- migration must be idempotent
- the system may not quietly double-publish or silently fork graph truth between stores

### Workstream C. Shell ↔ Kuzu ingest journal

Required output:

- the first real cross-store ingest journal between shell state and `Kuzu`
- at minimum:
  - `pending`
  - `published`
  - partial-failure visibility
  - resumable retry
  - idempotent replay
- store-agnostic coordination logic
  - each target store registers as a named publish target
  - the journal tracks per-target publish state
  - `19` must be able to add `Chroma` as a new target, not as a rewrite of the journal core

Hard rule:

- this mechanism is not optional
- this is the first phase where a second active storage motor becomes real
- Phase 19 may extend this journal to `Chroma`, but may not invent it from scratch
- `Kuzu` may be the first active target, but the journal core may not be hardcoded as a Kuzu-only coordinator

### Workstream D. Graph retrieval restoration

Required output:

- materially stronger graph retrieval than the current SQLite sort-and-package path
- graph outputs that improve:
  - relationship traversal
  - multi-hop usefulness
  - temporal recall usefulness
  - bounded inferred-link usefulness
- retrieval results that remain class-separated:
  - current explicit truth
  - historical truth
  - conflict
  - inferred link

Hard rule:

- packaging may expose this more clearly, but packaging alone does not count as success

### Workstream E. Local module thinning

Required output:

- `brainstack/graph.py` no longer acts as the effective graph-intelligence center
- `brainstack/db.py` no longer acts as the effective graph retrieval engine
- `brainstack/retrieval.py` stays a packaging layer, not a graph rescue layer
- `brainstack/usefulness.py` stays telemetry-only

Hard rule:

- if the old local path is still the effective graph center after the phase, the phase fails

### Workstream F. Deterministic local reconciliation boundary

Required output:

- a sharp line between:
  - donor-shaped graph intelligence
  - Brainstack-local deterministic publication logic

What may remain local:

- canonicalization
- idempotent publication rules
- explicit conflict-safe write decisions
- publish journal coordination

What may not remain local as a substitute for donor power:

- graph relevance rescue
- traversal simulation
- relationship reasoning that exists only because the graph backend is weak

### Workstream G. Eval ladder

Required output:

- Gate A:
  - graph contract tests
  - migration/bootstrap tests
  - journal tests
- Gate B:
  - graph usefulness scenarios
  - must prove better connected follow-up reasoning
- Gate C:
  - a bounded graph-heavy benchmark-derived or real-world subset
- Gate D:
  - bounded runtime smoke only if source-side proof leaves a real uncertainty

Hard rule:

- benchmark evidence may support the phase
- benchmark chasing may not define the phase

## Protected Boundaries

### L1 boundary

- `executive_retrieval.py` may receive richer graph results
- L1 may not need another conceptual rewrite
- if Phase 18 requires redesigning the L1 contract, the L2 contract is wrong

### L3 boundary

- Phase 18 may not sneak in the L3 backend migration
- temporary graph-side accommodations for current corpus seams are allowed only if they do not become permanent L3 substitutes

### Provider boundary

- `sync_turn()` remains non-blocking
- heavy graph work belongs in provider-local background/batch paths
- no synchronous turn-path graph migration or large traversal work

## Minimum Proof Required Before Calling Phase 18 Done

All of the following must be true:

1. the active graph center is no longer the old SQLite path
2. the shell↔`Kuzu` ingest journal exists and works
3. graph usefulness is materially stronger in realistic follow-up scenarios
4. explicit current truth stays primary
5. historical truth, conflict, and inferred links remain clearly separated
6. L1 benefits from richer graph results without another L1 rewrite

If any one of these is missing, the phase is not done.
