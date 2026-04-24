# Phase 12 Architecture Notes

Captured: 2026-04-11
Status: pre-planning note

## Important Design Constraint
Phase 12 must not stop at “extract some candidates”.

The Tier-2 core must follow:
- extractor
- then reconciler
- then write-policy

## Extractor → Reconciler Pattern

Verdict:
- required
- not overengineering
- mandatory for durable quality

Why it matters:
- without a reconciler, repeated facts keep duplicating
- changed facts do not supersede older ones cleanly
- graph/profile shelves become noisy and ambiguous

Expected reconciler outcomes:
- `ADD`
- `UPDATE`
- `NONE`
- `CONFLICT`

Meaning:
- `ADD` = genuinely new durable fact
- `UPDATE` = same durable slot, newer or corrected value
- `NONE` = already known, skip duplicate write
- `CONFLICT` = incompatible claim that should be surfaced or bounded

## Relation To Debounce
The debounce decision belongs architecturally to the Phase 11 foundation seam.
Phase 12 should consume that seam and perform real batch extraction/reconciliation on the resulting transcript batch.

## What Phase 12 Should Actually Do
- read a bounded transcript batch from the queue/trigger seam
- run multilingual Tier-2 extraction on that batch
- emit structured candidate objects
- reconcile those candidates against existing profile/graph state
- write only the reconciled outcome into Brainstack shelves

## Non-Goals
- do not write every extracted candidate blindly
- do not create a second reasoning engine with uncontrolled loops
- do not skip reconciliation just because extraction is working
- do not use language-specific regex expansion as a substitute for multilingual extraction

## Handoff To Phase 13
Phase 12 produces cleaner durable writes.
Phase 13 then adds:
- temporal supersession policy
- provenance normalization and merge
- safer visibility and recall policy
