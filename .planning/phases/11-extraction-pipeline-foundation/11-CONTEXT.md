# Phase 11 Context

## Goal
Split Brainstack ingest into explicit pipeline seams without creating a second runtime, a god object, or a language-specific heuristic pile.

## Why This Phase Exists
Phase 10.2 stops the bleed, but the provider still needs an explicit internal pipeline shape before Tier-2 can be added safely.

Without Phase 11:
- Tier-0 remains a local fix instead of a first-class seam
- Tier-2 has no clean scheduling entry point
- reconciler/write-policy can be bypassed accidentally
- the provider risks growing back into a mixed-responsibility object

## Required Seams
- Tier-0 hygiene slot
- Tier-1 bootstrap extractor slot
- Tier-2 extractor slot
- reconciler slot
- write-policy slot
- trigger / scheduling seam

## Design Constraints
- single Brainstack provider path only
- no second memory runtime
- no new memory layer
- no language-specific graph regex expansion
- debounce must be configurable and bounded
- extraction and write policy must be separable

## Minimum Acceptable Output
- Tier-0 and Tier-1 live in their own modules
- provider delegates to a pipeline module instead of inlining extraction logic
- Tier-2 scheduling contract exists now, even if the real worker arrives in Phase 12
- focused tests prove the provider is actually using the new seam

## Preferred Defaults
- Tier-2 idle window: 30 seconds
- Tier-2 batch turn limit: 5 turns

## Next Step
Phase 12 implements the real multilingual Tier-2 extractor and reconciler on top of these seams.
