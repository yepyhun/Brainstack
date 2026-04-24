# Phase 19 Implementation Contract

## Purpose

This document turns the Phase 19 plan into a concrete execution contract.

The goal is to prevent two failure modes:

- a “nice-looking” L3 refactor that keeps the old SQLite corpus center alive
- an overgrown rewrite that drags L1 and L2 back into the phase and loses control

## Required Workstreams

### Workstream A. Active L3 backend seam

Required output:

- an explicit corpus backend interface that is strong enough to host:
  - document / chunk publication
  - semantic retrieval
  - lexical retrieval support
  - bounded retrieval metadata for later packing
- a `Chroma`-default implementation path behind that seam

Hard rule:

- the seam must become the active corpus center
- it may not exist merely as an unused adapter beside the old SQLite corpus path

### Workstream B. SQLite -> Chroma bootstrap and migration

Required output:

- a repeatable bootstrap path from current local corpus state into `Chroma`
- clear distinction between:
  - initial migration/bootstrap
  - ongoing incremental publish
- fail-closed behavior if bootstrap is incomplete or inconsistent

Hard rule:

- migration must be idempotent
- the system may not quietly double-publish or silently fork corpus state between stores

### Workstream C. Shell ↔ Chroma journal extension

Required output:

- extension of the existing store-agnostic publish journal to `Chroma`
- at minimum:
  - `pending`
  - `published`
  - `failed`
  - partial-failure visibility
  - resumable retry
  - idempotent replay
- explicit reuse of the existing journal core rather than a corpus-specific parallel mechanism

Hard rule:

- `19` may add `Chroma` as a named publish target
- `19` may not rewrite the journal core invented in `18`
- the journal must surface per-target state clearly enough that shell↔`Kuzu` and shell↔`Chroma` divergence is visible and recoverable

### Workstream D. Raw corpus retrieval restoration

Required output:

- materially stronger corpus retrieval than the current SQLite FTS plus `LIKE` path
- corpus outputs that improve:
  - long-document recall
  - semantic relevance
  - retrieval under large corpus size
  - reuse of useful raw passages across follow-up turns

Hard rule:

- raw retrieval is the primary L3 strength
- the phase fails if raw retrieval is still effectively nominal while only packing improves

### Workstream E. Bounded packing restoration

Required output:

- packing that selects and orders better corpus candidates under token limits
- bounded reduction of overlap / duplication without erasing useful evidence
- stable, explainable ordering of retrieved corpus snippets

Hard rule:

- packing is a second-stage quality layer
- packing may not become the hidden rescue layer for weak retrieval
- compression-first design does not count as success if raw retrieval remains weak

### Workstream F. Local module thinning

Required output:

- `brainstack/corpus.py` no longer acts as the effective corpus-intelligence center
- `brainstack/db.py` no longer acts as the effective corpus retrieval engine
- `brainstack/retrieval.py` stays a packaging layer, not a corpus rescue layer
- `brainstack/donors/corpus_adapter.py` becomes a real seam, not a nominal wrapper

Hard rule:

- if the old local SQLite path is still the effective corpus center after the phase, the phase fails

### Workstream G. L1 semantic-leg activation

Required output:

- real semantic corpus signals flowing through the existing executive retrieval contract
- removal of the current degraded-by-design semantic corpus placeholder
- proof that L1 gains stronger corpus signals without another conceptual rewrite

Hard rule:

- if L1 still behaves as though the semantic corpus leg is absent or fake, the phase fails
- if Phase 19 requires conceptual redesign of the L1 contract, the L3 contract is wrong

### Workstream H. Eval ladder

Required output:

- Gate A:
  - corpus backend contract tests
  - bootstrap / journal tests
- Gate B:
  - corpus usefulness scenarios
  - must prove better large-document follow-up reasoning
- Gate C:
  - a bounded benchmark-derived corpus subset
- Gate D:
  - bounded runtime smoke only if source-side proof leaves a real uncertainty

Hard rule:

- benchmark evidence may support the phase
- benchmark chasing may not define the phase

## Protected Boundaries

### L1 boundary

- `executive_retrieval.py` may receive live semantic corpus signals
- L1 may not need another conceptual rewrite
- if Phase 19 requires redesigning the L1 contract, the L3 contract is wrong

### L2 boundary

- Phase 19 may consume the already-restored graph signals
- Phase 19 may not reset, redesign, or weaken the `Kuzu` graph center
- cross-store coordination must compose with the existing graph target rather than compete with it

### Provider boundary

- `sync_turn()` remains non-blocking
- heavy corpus publication / backfill belongs in provider-local background or batch paths
- no synchronous turn-path large corpus bootstrap or vector backfill work

## Minimum Proof Required Before Calling Phase 19 Done

All of the following must be true:

1. the active corpus center is no longer the old SQLite path
2. `Chroma` is integrated through the existing store-agnostic journal core as a named publish target
3. raw corpus retrieval is materially stronger in realistic long-document scenarios
4. bounded packing improves usefulness because retrieval candidates are better
5. the L1 semantic corpus leg is genuinely live
6. L2 remains intact and no new L1 redesign was required

If any one of these is missing, the phase is not done.
