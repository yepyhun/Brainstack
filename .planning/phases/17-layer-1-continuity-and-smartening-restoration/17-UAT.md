# Phase 17 UAT

## Verdict

Phase 17 verify passes.

## User-facing verification outcome

### 1. Smarter follow-up behavior and better connected recall

User verdict: `pass`

Important nuance captured during verification:

- the original wording was too weak and did not fully express the real goal
- the accepted version was stricter:
  - the agent should not merely remember more
  - it should better understand the important thread
  - and it should better surface which prior memories actually connect to that thread

This is now the reference interpretation of what “smarter” means for Phase 17.

### 2. Relevant recall may be broader, but must stay usable

User verdict: `pass`

Important nuance captured during verification:

- the earlier framing “do not bring in too much extra” was too restrictive
- the correct target is:
  - better to surface more connected prior material than to drop something important
  - but the answer must still stay coherent and usable
  - broader recall is acceptable
  - chaotic recall is not

### 3. Donor-first L1 must not fall back to keyword-jumping behavior

User verdict: `pass`

The user accepted that the current L1 no longer feels like a pure manual word-trigger path and can carry the same thread across different wording choices.

## Technical proof closed without repeated user questioning

- targeted Phase 17 source-side tests pass
  - focused suite: `30 passed`
- bounded eval ladder passes the fast gates
  - Gate A: `4 passed`
  - Gate B: `26 passed`
  - Gate C: explicit skip without `COMET_API_KEY` / `COMETAPI_API_KEY`
- integration-kit doctor dry-run passes
- integration-kit install carry-through passes

This technical carry-through was closed from direct proof rather than more repeated user confirmation, because that category had already been covered earlier and the user explicitly asked to avoid redundant questioning.

## What Phase 17 is considered to have proven

- the old handwritten Tier-1 path is no longer the effective center of L1 behavior
- L1 now behaves like an executive retrieval layer instead of another heuristic shelf
- the semantic leg is explicit and honest about its current degraded state
- the fast eval ladder now exists and can be rerun without mandatory rebuilds
- the user-facing direction is better:
  - smarter follow-up
  - better connected recall
  - less obvious keyword-jumping

## What remains intentionally open

- the donor-backed semantic leg is still not restored; it remains explicit `degraded` until later recovery phases
- a bounded live rebuild/runtime smoke may still be useful later, but only if source-side or eval-ladder checks surface a real doubt

This is not a Phase 17 failure. It is the expected remaining gap after restoring the L1 shape first without forcing the later embedded-backend migrations into the same phase.
