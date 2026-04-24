# Phase 58 Implementation Contract

## invariant

Phase 58 must leave the project in a cleaner and more inspectable state than Phase 57, without adding any new capability scope.

The phase succeeds only if all four surfaces agree:

- source-of-truth repo
- installed runtime
- persistent state
- planning / proof artifacts

## canonical principle reference

Use the canonical principles file directly:

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`

Pinned names that must govern this phase:

- `Donor-first`
- `Modularity / Upstream updateability`
- `Fail-closed upstream compatibility`
- `No benchmaxing`
- `Truth-first / no "good enough"`
- `Zero heuristic sprawl`
- `Multimodal-first architecture`
- `The donor-first elv marad`

## required properties

- all touched fixes originate in `Brainstack-phase50`
- the installer/wizard path reproduces them onto `finafina`
- the source-of-truth repo ends clean and releasable
- persistent-state cleanup is real:
  - not just hidden in rendering
  - not just ignored in queries
  - not just overwritten by newer rows
- dead or half-wired shipped surfaces receive an explicit keep/remove/demote decision
- any kept compatibility surface is bounded and documented
- planning artifacts no longer contradict the actual runtime or repo state

## prohibited outcomes

- cleaning only the target runtime while leaving the source repo dirty
- removing source files based only on automated dead-code heuristics without runtime-entry validation
- hiding contaminated persistent rows while leaving them in place as silent residue
- retaining stale behavior/style governor residue because it is currently harmless
- declaring inspector readiness while manual-gate or stale-audit wording still says otherwise
- using new heuristics, prompt tricks, or user-specific patches to make the phase look cleaner than it is

## proof expectation

Proof must include:

- git cleanliness / diff proof for `Brainstack-phase50`
- installer/doctor proof on `finafina`
- persistent-state proof from the live installed runtime
- targeted tests for every debt family touched
- updated planning files that explicitly close or remap the old debt wording

## output required

- execution result with:
  - what was removed
  - what was demoted
  - what was kept and why
  - what persistent-state residue was scrubbed
  - what release boundary was cut
- if any residue remains, it must be named explicitly as residual risk, not left implicit

## anti-goals

- no new feature work
- no new authority lanes
- no new extraction cleverness
- no “good enough” closure from partial cleanup
