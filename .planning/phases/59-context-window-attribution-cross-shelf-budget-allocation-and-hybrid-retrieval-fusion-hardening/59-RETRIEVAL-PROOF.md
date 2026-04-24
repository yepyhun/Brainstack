# Phase 59 Retrieval Proof

## Synthetic fusion proof

- installed code path result:
  - `FUSION_ORDER ['continuity:1', 'transcript:11', 'corpus:9:0']`
- accepted interpretation:
  - a candidate supported by both keyword and semantic channels now outranks a transcript keyword-only candidate in the proof harness

## Synthetic allocator proof

- ranked candidate order:
  - `['continuity:1', 'transcript:2', 'graph:state:3', 'operating:5', 'corpus:4:0']`
- with `evidence_item_budget = 3`:
  - total selected evidence rows = `3`
- with `evidence_item_budget = 5`:
  - total selected evidence rows = `5`

This verifies that the new shared allocator now gates total selected evidence rows across shelves instead of relying only on independent shelf caps.

## Live-adjacent proof on current Bestie DB

- tested queries on the installed runtime selected only `3-5` Brainstack evidence rows
- accepted interpretation:
  - the allocator exists and works
  - the current live complaint is still partly host-stack size, not a giant Brainstack packet on every turn
