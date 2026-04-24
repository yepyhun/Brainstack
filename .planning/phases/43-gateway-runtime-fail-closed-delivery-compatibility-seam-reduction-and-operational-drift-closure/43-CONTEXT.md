# Phase 43 Context

## problem statement

Phase 41 showed that the gateway/runtime layer still contains:

- explicit best-effort fallback delivery
- deprecated compatibility seams in boot/runtime config bridging
- fallback-model and restart-on-failure behavior mixed into the main runtime path
- warning surfaces where provider economics, runtime drift, and source logic can blur together

That means the product can still work while remaining unpleasant to inspect.

## why this phase exists

- a strict inspector will look at user-visible fallback and runtime semantics, not just memory correctness
- if the gateway path still leans on best-effort seams, the product remains easier to criticize than it should be

## findings this phase is intended to close

- Phase 41 Batch 1:
  - 2. Route-resolution and auxiliary payment failures
  - 3. CA bundle path drift
- Phase 41 Batch 4:
  - 10. Gateway stream delivery still contains explicit best-effort fallback seams
  - 11. Gateway boot/runtime still carries deprecated compatibility and fallback model seams

## architectural posture

- do not hide runtime uncertainty
- do not convert operational ambiguity into more logging only
- keep source-vs-deploy-vs-economic failure classification explicit

## canonical principle reference

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`

## recommended model level

- `xhigh`
