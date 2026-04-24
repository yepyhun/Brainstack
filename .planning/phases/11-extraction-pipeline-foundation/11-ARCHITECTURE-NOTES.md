# Phase 11 Architecture Notes

Captured: 2026-04-11
Status: pre-planning note

## Important Design Constraint
Phase 11 should not treat Tier-2 execution timing as an afterthought.

The ingest pipeline foundation must explicitly define:
- Tier-0 hygiene slot
- Tier-1 bootstrap extractor slot
- Tier-2 extractor slot
- reconciler slot
- write-policy slot
- trigger / scheduling seam

## Debounce Pattern

Verdict:
- required
- not overengineering
- not a new memory layer
- not a separate runtime

Why it matters:
- without debounce, Tier-2 would fire on every turn
- that creates repeated LLM calls on the same still-unfolding topic
- cost rises
- duplicate candidates rise
- noise rises

Preferred role of Phase 11:
- define the scheduling seam now
- make the trigger contract explicit before Phase 12 implementation

Recommended default shape:
- batch Tier-2 work after either:
  - short idle window, e.g. ~30 seconds of silence
  - or bounded turn count, e.g. ~5 turns
- keep this as a configurable policy, not a hardcoded benchmark trick

What Phase 11 must leave behind:
- a clear place in the pipeline where Tier-2 work is queued or scheduled
- a clear contract for what input batch gets passed forward
- proof that this does not create a second memory runtime or bypass the single Brainstack provider path

## Anti-Patterns
- do not run Tier-2 on every single user turn by default
- do not hide scheduling inside ad hoc provider branches
- do not make debounce a language-specific heuristic
- do not turn scheduling into a giant orchestration subsystem in Phase 11

## Handoff To Phase 12
Phase 11 should prepare the trigger/seam.
Phase 12 should activate the actual Tier-2 worker/extractor behavior on that seam.
