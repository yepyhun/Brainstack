# Phase 57 Implementation Contract

## invariant

The product is not inspector-ready until the installed Discord runtime can handle ordinary turns without silent hangs, degrade cleanly when Brainstack graph/provider paths are unhealthy, speak truthfully about scheduler/reminder creation, and keep raw reset lifecycle text off the user-facing surface.

This contract does not assume Brainstack is the sole cause.
It requires the runtime boundary to be corrected end to end.

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

1. An ordinary Discord turn cannot stay live indefinitely with no answer and no bounded failure result.

2. If Brainstack provider initialization fails, the runtime must not continue in a misleading partial-active state.

3. If the graph backend is unavailable or unhealthy:
   - active request paths must degrade cleanly
   - repeated publish/search churn on a dead backend is not acceptable

4. Reminder scheduling acknowledgements must be truthful:
   - success only after real native scheduler registration succeeds
   - failure must be surfaced explicitly

5. User-facing reset behavior must be clean:
   - no bare `Session reset.`
   - no raw lifecycle/status leakage in ordinary conversation

6. The fix must be reproducible by install/copy from:
   - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`

## prohibited outcomes

- adding prompt-only obedience steering to hide the underlying runtime defect
- adding user-specific or locale-specific logic to rescue the current Discord case
- faking reminder success by storing a reminder fact in memory without a real scheduled job
- masking reset leakage while the underlying lifecycle text still traverses the runtime path
- claiming a hang is solved while the run still only clears when `/reset` is invoked
- calling the phase complete from log cleanliness alone without real Discord UI proof

## proof expectation

Proof must show:

- installed runtime reproduction from source of truth
- no stuck ordinary turn on the installed runtime
- no half-open graph/provider residue during the tested request path
- successful short-horizon native reminder creation and delivery
- clean reset surface on real Discord UI

## output required

- one explicit execution result artifact
- one live-runtime stuck-run proof note
- one scheduler truth proof note
- one final Discord UI proof note

## anti-goals

- no new capability work
- no behavior-governor regression
- no benchmark-driven tuning
- no fake success semantics on reminder or reset behavior
