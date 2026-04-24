# Phase 28 Context

## Why this phase exists

Phase `27` and `27.1` closed one bounded donor thread cleanly:

- selective `hermes-lcm` host-level uptake landed only where ROI was strong
- Bestie mirroring proved a narrow diagnostics win
- no broader retrieval/product uplift was claimed without evidence

That leaves a different question open:

- the core upstream donors have moved again
- Brainstack should not drift away from useful donor changes just because local code is already working
- but donor freshness alone is not a reason to ship more code

The correct next move is therefore a bounded **upstream donor delta audit**:

- compare current Brainstack seams against the latest upstream donor deltas
- adopt only the slices that are both:
  - materially useful
  - low enough maintenance burden
- explicitly no-op or defer the rest

## Latest donor reading at planning time

### Hindsight

Current reading:

- latest upstream shows one concrete candidate with direct Brainstack relevance:
  - bounded recall-budget mapping / adaptive retrieval breadth
- this maps onto Brainstack's real tension between:
  - token discipline
  - recall width
  - route-specific evidence selection

Current hypothesis:

- there may be a thin Brainstack-owned budget policy worth adopting or adapting

### MemPalace

Current reading:

- latest upstream reinforced backend-boundary discipline around Chroma
- local Brainstack already has:
  - `brainstack/corpus_backend.py`
  - `brainstack/corpus_backend_chroma.py`
- current local scan suggests direct `chromadb` usage is already confined to the backend layer

Current hypothesis:

- this may collapse to audit-only / no-op
- if any win exists, it should be a thin boundary hardening, not a feature port

### Graphiti

Current reading:

- latest visible upstream movement did not surface a strong immediate runtime-ROI candidate for Brainstack
- no clear graph-truth delta has yet justified new work here

Current hypothesis:

- Graphiti should stay explicit no-op unless the audit finds a concrete missed win

## Settled truths this phase must preserve

- this is **not** a blanket donor sync phase
- this is **not** a new donor-transplant phase
- this is **not** a Bestie-first phase
- Brainstack source remains the implementation source of truth
- Bestie remains a later mirror/validation target only if something real lands
- the settled Phase `22` boundary remains intact
- the settled Phase `24/25` correctness and broader live baseline remain intact
- the settled Phase `27/27.1` reading remains intact:
  - bounded host-level donor uptake worked narrowly
  - measured diagnostics value is acceptable
  - fake broader claims are forbidden

## Core question

Which latest upstream donor deltas are actually worth pulling toward Brainstack now, given the current product path, donor-first doctrine, and maintenance constraints?

## Acceptable answers

- one donor slice is worth thin adoption now
- one donor slice is worth a thin hardening/audit fix only
- none of the current latest deltas justify code change right now

All three answers are acceptable if they are proven honestly.

## Why this phase is worth doing

This phase is worth doing because:

- it can catch a real donor-aligned leverage win without reopening broad architecture work
- it can prevent fake “latest upstream must be better” thinking
- it can reduce future donor drift by making the current delta explicit

But it is only worth doing if it stays bounded.

If the audit expands into broad sync or new local glue, the phase should stop.
