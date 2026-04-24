# Phase 27 Context

## Why this phase exists

The `hermes-lcm` donor audit established a clear split:

- the donor is a host-level lossless context-management system
- our current stack uses:
  - host-level context compression in Hermes
  - Brainstack for continuity, profile, graph truth, and retrieval support
- the donor is **not** actually integrated as a live plugin in our runtime
- only a narrow continuity/transcript pattern has been adopted locally so far

That means the right next move is **not** full donor integration.
The right move is a bounded, donor-first uptake of the small set of host-level ideas that can improve auditability, state clarity, and compacted-history ergonomics without creating a second runtime or a second truth owner.

Just as important:

- the target is not “integrate the donor”
- the target is “materially improve the current system”
- if a donor slice turns out to add more maintenance burden, fragility, or operator headache than real product value, it must be stopped and left out

## What the donor audit established

### Stronger than expected

- `hermes-lcm` has a clean host-level design for:
  - source-window provenance
  - lifecycle/frontier state
  - bounded compacted-history expansion/search
  - optional session filtering for noisy/stateless sessions
- several of these donor slices are modular enough to be adopted as patterns or thin modules

### More limited than a naive reading

- the donor is built around a `ContextEngine` slot that our current Hermes host does not expose
- full `LCMEngine` adoption would require a host architecture change, not thin wiring
- the donor's immutable store + DAG + tool stack is not a drop-in replacement for Brainstack or for the current host compressor

### Current reading

- the highest-ROI donor candidates are:
  - source-window / compaction provenance
  - explicit lifecycle / frontier state
  - bounded expand/search ergonomics over compacted history
- the only conditional candidate is:
  - ignored/stateless-session filtering
- anything beyond that is likely to become hidden host rewrite work
- the current Brainstack baseline already has partial overlap in some places:
  - provenance / snapshot support: partial
  - bounded snippet/search shaping: partial
  - lifecycle/frontier state: largely absent
  - ignored/stateless-session filtering: effectively absent
- therefore the phase must begin with a duplicate/overlap audit before writing any code

## Core doctrine for this phase

- this is a **selective host-level donor uptake** phase
- it is **not** an `LCM` integration phase
- it must improve the host layer around compaction and compacted-history handling
- it must preserve Brainstack as the durable memory owner
- it must preserve the settled Phase `22` boundary
- it must preserve the settled Phase `25` baseline reading
- implementation source of truth belongs in the Brainstack repo first
- the Bestie repo is only for later validation/mirroring if the Brainstack-side result proves out

## Project guardrails with refreshed emphasis

- donor-first
  - prefer lifting isolated donor patterns or modules over inventing local replacements
- utility-first
  - if a donor slice does not produce clear product value, do not ship it just because it is available
- modularity / upstream updateability
  - keep any new logic isolated and keep native host edits thin
- truth-first
  - if a donor slice is too coupled to the full `LCMEngine`, say so and stop
- no parallel runtime
  - do not create a second compaction/runtime system beside the current host compressor
- no token bloat
  - no feature is allowed to raise ordinary-turn token use without a clear, bounded payoff
- no overengineering
  - if a donor benefit requires a context-engine slot rewrite, it is out of scope for this phase

## Target architecture after Phase 27

- Hermes host still owns host-side context compression through its native compressor path
- Brainstack still owns durable memory, continuity shelves, profile truth, and retrieval support
- selected `hermes-lcm` donor slices may exist only as:
  - provenance enrichment
  - lifecycle/frontier bookkeeping
  - bounded compacted-history inspection ergonomics
  - conditional session filtering if the evidence justifies it
- there is still no second runtime compactor and no second durable truth owner

## End-state invariants

- the host compressor remains the only active host-side compaction owner
- Brainstack remains the only durable personal/project memory owner on the owned axis
- compacted-history provenance becomes more inspectable, not more opaque
- lifecycle state becomes more explicit, not more magical
- any expand/search improvement remains bounded and token-aware
- session filtering is only adopted if noisy/stateless-session evidence is real

## What this phase is not

- not full `hermes-lcm` integration
- not a new `ContextEngine` slot project
- not a host rewrite
- not a Brainstack capability phase
- not a SHIBA-style uplift phase
- not dual-writing the same implementation in Brainstack and Bestie

## Ideal outcome

The host layer becomes easier to reason about and less black-box around compaction, while the project avoids taking on a second full context-management runtime or a maintenance-heavy donor vanity integration.
