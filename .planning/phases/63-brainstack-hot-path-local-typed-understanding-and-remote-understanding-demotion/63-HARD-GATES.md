# Phase 63 Hard Gates

## 1. no-mandatory-remote-hot-path gate

- the phase must not close while ordinary task/operating read and capture behavior still depends on successful remote `structured_understanding` as mandatory authority

## 2. no-heuristic-sprawl gate

- the phase must not reintroduce cue lists, phrase farms, locale dictionaries, or renamed keyword routing anywhere in the Brainstack hot path

## 3. local-typed-authority gate

- the chosen design must state exactly which local typed substrates carry authority for ordinary task/operating decisions
- "it figures it out locally somehow" is not enough

## 4. read-path-discipline gate

- task lookup, operating lookup, current-work lookup, and current-state lookup must not collapse back into one fuzzy text-intent bucket

## 5. write/capture-discipline gate

- capture eligibility must be explicitly bounded
- ambiguous ordinary turns must not be silently over-captured just because the remote seam is being removed

## 6. multimodal gate

- the architecture must remain valid for mixed-modality or non-text turn envelopes
- a text-token-only design fails this gate

## 7. no-shadow-host-classifier gate

- execution must not move the same classification dependency into Hermes host code or a side helper and call that "local"

## 8. no-session-search-rescue gate

- `session_search`, transcript dumping, or other tool fallback must not be used as the primary answer to ordinary Brainstack route/capture authority

## 9. no-rollback gate

- the recovery target is not `v1.0.16`
- any design that depends on restoring old heuristic routing fails

## 10. current-state-separation gate

- Phase `62` live-state authority must remain a separate typed concern
- the new hot-path architecture must not blur current-state truth back into generic recap/task routing

## 11. source-of-truth gate

- planning and later execution must reflect the actual current Brainstack source, not a simplified memory of earlier releases

## 12. truth-first closeout gate

- final closeout must say plainly whether the remote seam is actually demoted from hot-path authority or only better contained

## 13. inspector gate

- a strict reviewer must be able to see:
  - the exact local substrates
  - the exact removed hot-path remote dependencies
  - the absence of heuristic routing
  - the preserved separation between live-state authority and ordinary task/operating understanding
