# Phase 19 Context

## Discuss Outcome

The Phase `19` direction is now explicitly locked.

This phase is **not** allowed to:

- keep SQLite as the active long-horizon corpus retrieval center
- treat “it stores documents” as success
- hide weak corpus retrieval behind nicer rendering or more aggressive trimming
- redesign L1 or L2 instead of restoring L3 power
- make compression-first the headline if raw corpus retrieval remains the stronger donor path

Phase `19` must replace the current nominal corpus shelf with a donor-first primary path.

## What “Donor-First L3” Means

For Phase `19`, the primary L3 behavior must be:

- embedded `Chroma`-style vector retrieval as the active corpus retrieval center
- donor-shaped raw corpus retrieval as the primary strength
- bounded packing that improves usefulness under token limits without becoming a fake substitute for weak retrieval
- a stable output seam so L1 can consume stronger corpus signals without another conceptual rewrite

This phase is not a generic document platform build.
It is the corpus restoration step for the existing single-provider Brainstack architecture.

## Brainstack Job vs Donor Job

### Brainstack job

- keep the shell state coherent
- extend the existing store-agnostic publish journal to a second publish target beyond `Kuzu`
- own cross-store consistency, partial-failure visibility, retry, and publish-state transitions
- preserve non-blocking provider behavior
- package donor-backed corpus results for L1 and the final model context
- keep installer / doctor / integration ownership

### Donor job

- provide the actual long-horizon corpus retrieval strength
- surface relevant raw passages and chunks from large material
- supply usable semantic retrieval signals to L1
- enable stronger bounded packing because the retrieval candidates are better, not because local glue becomes smarter

## Why This Phase Exists

The current local L3 still behaves mostly like:

- SQLite corpus tables
- FTS plus `LIKE`
- local section splitting
- local render-time trimming

That is not donor-restored corpus power.

MemPalace was chosen because it promised strong long-document handling and useful bounded recall from large material.
Phase `19` must make that claim defensible again.

## Hard Rule: Raw Retrieval First

The accepted donor reading is:

- raw corpus retrieval is the primary strength
- packing and compression are secondary helpers

So Phase `19` must not pass by saying:

- “packing got prettier”
- “token count went down”
- “document storage is cleaner”

if the actual long-horizon retrieval is still weak.

## Cross-Store Consistency Rule

Phase `18` introduced the first real store-agnostic publish journal with `Kuzu` as the active target.

Phase `19` must:

- extend that journal to `Chroma`
- keep the journal core store-agnostic
- register `Chroma` as a named publish target
- track per-target publish state
- preserve:
  - `pending`
  - `published`
  - `failed`
  - resumable retry
  - idempotent replay

Phase `19` may not replace the journal core with a corpus-specific special case.

## L1 Contract Impact

The semantic leg in Phase `17` is currently explicit and degraded-by-design.

Phase `19` is the phase that must finally make that leg real with donor-backed corpus retrieval.

Important constraint:

- L1 should receive better corpus signals through the existing executive retrieval contract
- Phase `19` may enrich L1 behavior
- Phase `19` may not force another conceptual L1 redesign

## High Acceptance Bar

Phase `19` is not allowed to pass on:

- “corpus support exists”
- “the backend changed”
- “packing looks cleaner”

The bar is:

- materially stronger large-document recall
- materially better retrieval of relevant raw passages
- bounded packing that helps because candidate selection is better
- semantic corpus retrieval that is honestly live, not fake

If the result still feels like:

- SQLite corpus shelf plus nicer trimming

then Phase `19` fails.

## Eval Ladder

The benchmark is not the purpose.
Real corpus usefulness is the purpose.

But the phase still needs a bounded proof ladder.

### Gate A: Fast corpus contract suite

- backend contract tests
- bootstrap / publish journal tests
- idempotence / failure-state tests

### Gate B: Corpus usefulness suite

- long-document follow-up scenarios
- must prove better recall from large material
- must prove semantic retrieval is genuinely live

### Gate C: Small benchmark-derived subset

- only as a regression guard
- not as the phase definition

### Gate D: Bounded runtime smoke

- only if source-side proof leaves a real doubt

## Non-Negotiable Rule

The benchmark may confirm success.
It may not define success by itself.

The core goal of Phase `19` is:

- large material becomes actually retrievable and useful
- semantic corpus retrieval becomes real
- bounded packing helps because retrieval is stronger, not because the shell got more decorative

## Recommended Effort

- `xhigh`
