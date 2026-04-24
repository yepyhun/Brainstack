# Phase 26 Implementation Contract

## Objective

Harden proactive continuity after reset so the system reliably resumes the user’s plan under stricter gates, without reopening settled architecture decisions or growing a new subsystem.

## System doctrine this phase must preserve

- Brainstack remains the owner of durable personal-memory truth.
- Phase 22 boundary decisions remain the default baseline.
- Phase 24 profile-isolation truth remains settled.
- Phase 25 remains the current broader live baseline.
- The project guardrails remain active and must be used explicitly:
  - donor-first
  - modularity / upstream updateability
  - truth-first
  - fail-closed on the owned axis
  - no benchmaxing
  - no overengineering

## Four mandatory strict filters

### 1. Event-frame restoration filter

- A pass requires more than recalling fragments.
- The answer must restore the larger plan/event frame without user nudging.

### 2. No-detour proactive filter

- If memory support is already sufficient, the answer must not first do one of these:
  - ask the user to restate the goal
  - drift into browsing/searching
  - seek tools as a substitute for continuing the known plan

These two filters are mandatory acceptance gates for this phase.

### 3. Selective-recall filter

- A pass does not mean replaying the whole remembered context.
- The answer should restore only the smallest useful set of:
  - event frame
  - active constraints
  - next-step-relevant details
- If the answer becomes token-wasteful or noisy, it fails this filter.

### 4. Whole-path diagnosis filter

- This phase must not assume the memory kernel is the only control point.
- A valid diagnosis must explicitly consider:
  - memory supply
  - routing / policy
  - answer synthesis
  - response packaging
  - detour behavior

All four filters are mandatory acceptance gates for this phase.

## Workstream A: Stricter proactive canary

- define and codify stricter proactive pass/fail evaluation
- include both:
  - event frame present
  - no-detour first move
  - selective minimal answer payload
  - whole-path diagnosis requirement

Required artifact:

- one stricter proactive canary / harness definition

## Workstream B: Passing vs failing trace comparison

- compare successful and unsuccessful proactive runs
- inspect:
  - packet composition
  - route / policy snapshot
  - persisted state
  - answer form
  - answer size / packaging selectivity

Protected rule:

- do not guess at the seam if the traces do not actually support the claim

## Workstream C: Seam diagnosis

- classify the remaining weakness as one of:
  - memory-supply seam
  - continuation-synthesis seam
  - routing / policy seam
  - response-packaging seam
  - future capability gap

Protected rule:

- no broad redesign without proof

## Workstream D: Bounded repair

- patch only the proven seam
- keep the repair thin and maintainable

Protected rule:

- no layered prompt band-aids around an unfixed deeper seam

## Workstream E: Stricter rerun and safety net

- rerun the proactive proof under the stricter filters
- rerun a small negative-control / safety net to ensure:
  - no fabricated event frame
  - no unnecessary re-ask
  - no unnecessary tool detour
  - no unnecessary verbose replay

Protected rule:

- a fix does not count if it only changes style while still failing the stricter gates

## Protected boundaries

### Anti-overengineering boundary

- no broad retrieval redesign
- no new planner subsystem
- no general intelligence expansion hidden inside a one-residual fix

### Boundary-stability / donor-risk boundary

- Phase 22’s coexistence decision remains in force unless direct evidence falsifies it
- Phase 24’s profile-isolation seam remains in force unless direct evidence falsifies it

### Truth boundary

- distinguish memory-supply failure from synthesis failure
- distinguish helpful continuation from tool-driven avoidance behavior
- distinguish concise proactive help from token-wasteful replay

## Minimum evidence required before calling Phase 26 done

- one stricter proactive canary
- passing/failing proactive trace comparison
- one proven seam classification
- one bounded fix if justified
- stricter rerun proof
- one small safety-net rerun showing no new detour drift
- explicit confirmation that the answer remains selective rather than bloated
