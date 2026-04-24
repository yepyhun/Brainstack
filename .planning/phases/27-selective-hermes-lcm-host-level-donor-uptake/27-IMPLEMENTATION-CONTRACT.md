# Phase 27 Implementation Contract

## Objective

Execute a bounded, donor-first uptake of the few `hermes-lcm` host-level ideas that are both portable and worthwhile, while refusing any hidden slide into full donor runtime integration, duplicate local rewrites, or negative-ROI maintenance burden.

## System doctrine this phase must preserve

- host compaction remains owned by the current Hermes host compressor path
- Brainstack remains the durable memory owner
- donor-first means import/adapt where cleanly possible
- donor-first does **not** mean transplanting the entire donor architecture
- token discipline remains a hard product rule
- Brainstack is the implementation source of truth for this phase
- Bestie is a later validation/mirror target only

## Workstream A: Donor portability truth

- produce a slice-by-slice portability read for:
  - source-window provenance
  - lifecycle/frontier state
  - bounded expand/search
  - session filtering
- for each slice, classify it as:
  - portable now
  - portable only as pattern, not code
  - not portable without architecture churn

## Workstream A.1: Duplicate / overlap audit

- prove whether the candidate slice is:
  - absent
  - partially present in Brainstack already
  - already good enough and not worth touching
- if the slice is partially present, extend the existing Brainstack seam instead of introducing a second parallel structure

## Workstream B: Source-window / compaction provenance

- adopt the donor's strongest provenance ideas at the host seam
- ensure compacted summaries or snapshots can be traced back to the bounded raw-source window they came from
- implementation must stay thin and must not require donor DAG runtime adoption
- stop immediately if the result would only improve “architectural neatness” without giving better auditability or safer expansion behavior

## Workstream C: Explicit lifecycle / frontier state

- add the smallest viable host-side lifecycle/frontier bookkeeping that improves reset/rollover/compaction clarity
- keep it as a minimal substrate, not a broad session-management framework
- stop if the donor state model cannot be reduced to a thin Brainstack-owned seam

## Workstream D: Bounded expand/search decision

- test whether compacted-history expand/search ergonomics can be improved without:
  - new unbounded tools
  - prompt bloat
  - a second memory owner
- if the bounded version is real and useful, implement it
- if not, defer it explicitly inside the phase closeout instead of forcing it through
- implementation is only acceptable if ordinary-turn token cost remains bounded and the UX becomes more precise rather than noisier

## Workstream E: Conditional session filtering

- inspect whether ignored/stateless-session filtering has real noise to remove in our runtime
- if the evidence is weak, do not ship it
- if the evidence is strong, implement only the narrowest useful version
- do not ship it just because the donor has it

## Workstream F: Proof

- prove host compaction still behaves correctly
- prove no Phase `22` boundary regression
- prove no ordinary-turn token inflation beyond the bounded design intent
- prove any shipped donor slice is easier to audit, not harder
- prove the Brainstack-first implementation can be mirrored into Bestie without re-designing it there

## Protected boundaries

### Anti-overengineering boundary

- no full `LCMEngine` port
- no new context-engine slot
- no second compaction runtime
- no broad host rewrite
- no feature with obvious maintenance pain and marginal user value

### Donor-first boundary

- prefer isolated donor files or very narrow donor patterns
- if a feature can only be copied by rewriting half of it locally, stop and defer it
- if a feature requires parallel hand-written implementations in Brainstack and Bestie, stop and redesign or defer it

### Ownership boundary

- Brainstack must remain the only durable memory owner
- host-level expand/search must never become a second durable truth channel

### Token boundary

- no ordinary-turn token growth without explicit proof that the tradeoff is worth it
- bounded expand/search must stay opt-in and compact

### Truth boundary

- if the donor slice is less portable than expected, record that honestly
- do not claim “LCM integrated” when the reality is selective uptake only

## Minimum evidence required before calling Phase 27 done

- a written portability verdict for all four candidate slices
- a written duplicate/overlap verdict for all four candidate slices
- shipped provenance improvement or an explicit falsified reason not to ship it
- shipped lifecycle/frontier improvement or an explicit falsified reason not to ship it
- a clear shipped-or-deferred verdict for bounded expand/search
- a clear shipped-or-deferred verdict for session filtering
- proof that the settled Brainstack/native boundary still stands
- proof that the shipped implementation is Brainstack-first and mirrorable, not duplicated by hand
