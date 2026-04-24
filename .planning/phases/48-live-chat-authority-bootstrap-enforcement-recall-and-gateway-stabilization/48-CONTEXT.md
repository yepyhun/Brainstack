# Phase 48 Context

## problem statement

The recent live Bestie chat failure is not one isolated bug. It exposed a multi-layer break where:

- live style authority remained polluted
- compiled behavior policy could be absent in the live store
- final-output enforcement became too soft when compiled authority was missing
- natural rule questions failed to route to the style owner
- transcript persistence failed on the host side
- operator traces leaked into the user-facing chat
- reminder scheduling semantics drifted away from intended local time

## why this phase exists

The user plans to wipe the polluted live memory store. That wipe can reset the bad historical state, but it does not by itself make the product dependable. The runtime must bootstrap into a clean authority lane after reset and stay stable in ordinary live chat without requiring future manual wipes.

## findings this phase responds to

- live `behavior_contracts` authority can remain polluted while compiled policy is absent
- typed invariant enforcement can go inactive in live operation
- implicit style recall is still too narrow on natural phrasing
- gateway transcript persistence has a live field-mismatch bug
- tool traces still leak into the user-facing chat stream
- reminder scheduling correctness is not trustworthy enough

## architectural posture

- this is a live product stabilization phase, not benchmark work for one prompt
- the fix must improve the kernel-plus-host path as one coherent product surface
- canonical truth, ordinary-turn behavior, continuity persistence, and user-facing UX must converge rather than getting patched separately
- no heuristic farms, no regex-net rescue layer, and no recurring operational wipe requirement are acceptable outcomes

## canonical principle reference

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`
- pinned names:
  - `Donor-first`
  - `Modularity / Upstream updateability`
  - `Fail-closed upstream compatibility`
  - `No benchmaxing`
  - `Truth-first / no "good enough"`
  - `Zero heuristic sprawl`
  - `Multimodal-first architecture`

## recommended model level

- `xhigh`
