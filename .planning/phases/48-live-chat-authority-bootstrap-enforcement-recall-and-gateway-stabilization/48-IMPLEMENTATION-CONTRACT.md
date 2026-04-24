# Phase 48 Implementation Contract

## invariant

After a live memory wipe, the runtime must be able to bootstrap one clean style authority, enforce its typed invariants in final output, answer natural rule-recall questions from the correct owner, persist transcript continuity correctly, keep internal tool traces off the user-facing chat surface, and schedule reminders with correct local-time semantics.

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

## required properties

- no active style authority may coexist with a missing compiled policy without repair or explicit fail-closed behavior
- no final output may silently ship while active typed invariants remain unenforced
- natural style-rule questions must resolve to style authority rather than transcript recall when style authority exists
- transcript persistence must succeed on the live gateway path for normal chat turns
- internal tool traces must not leak into the user-facing chat stream
- reminder scheduling must be anchored to intended local/user time semantics
- the phase must prove the complete post-wipe live path, not just source-only unit behavior

## prohibited outcomes

- solving the incident with one-off wording hacks or benchmark-specific prompts
- adding broader heuristic routing or regex farms in place of owner-derived signals
- relying on repeated manual memory wipes as the ongoing operating model
- hiding live failures behind softer wording while the underlying authority or persistence seam remains broken

## required verification artifact

- one end-to-end wiped-store proof that demonstrates:
  - clean authority bootstrap
  - compiled policy presence
  - compliant ordinary reply
  - correct natural style recall
  - successful transcript persistence
  - no tool-trace leak
  - correct reminder time semantics

## recommended model level

- `xhigh`
