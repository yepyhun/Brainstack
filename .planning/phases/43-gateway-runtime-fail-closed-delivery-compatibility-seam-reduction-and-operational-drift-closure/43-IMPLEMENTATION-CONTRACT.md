# Phase 43 Implementation Contract

## invariant

This phase must make runtime behavior more explicit and less compatibility-heavy without sacrificing truthful recovery behavior.

## canonical principle reference

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`
- pinned names:
  - `Donor-first`
  - `Fail-closed upstream compatibility`
  - `Truth-first / no "good enough"`
  - `Zero heuristic sprawl`
  - `Multimodal-first architecture`

## required properties

- no new silent delivery fallback
- no new deprecated env or provider fallback seams
- runtime warnings and failures must remain classifiable as:
  - source defect
  - deploy drift
  - provider/economic failure
- any unavoidable fallback must be explicit, bounded, and test-covered

## prohibited outcomes

- burying runtime ambiguity behind generic warning text
- expanding compatibility shims because they are convenient
- introducing new operator-only knowledge that is not encoded in code/tests

## required verification artifact

- verification notes proving closure or explicit quarantine of the Batch 1 / Batch 4 runtime findings from Phase 41

## recommended model level

- `xhigh`
