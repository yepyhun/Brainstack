# Phase 26 Context

## Why this phase exists

Phase 25 refreshed the broader deployed-live baseline after the Phase 24 fixes.

That rerun showed a cleaner residual map, but one narrow weakness remained:

- `proactive_continuity_after_reset`

The important reading from Phase 25 is:

- this is **not** a broad correctness regression
- this is **not** a reason to reopen the Phase 22 boundary
- this is **not** a reason to reopen the Phase 24 profile-isolation seam

Instead, it looks like a narrower live proactive continuity robustness problem.

## What is already known

### Settled truths

- durable profile isolation now holds in the broader live baseline
- the broader top-line score remains `9 / 10`
- the remaining proactive miss is intermittent, not fully deterministic:
  - focused variance check: `2 / 3` pass

### What still needs to be improved

- the system does not always carry forward the **event frame** strongly enough after reset
- it can remember details like:
  - venue
  - dietary constraint
- while still dropping the larger “what are we continuing?” frame

There is also a practical UX risk:

- when memory support is already sufficient, the model should not fall into:
  - asking the user to restate the goal
  - or trying tool/web lookup as a substitute for continuing the plan

## Core doctrine for this phase

This is a focused robustness phase.

It is not:

- a broad new memory-capability phase
- a SHIBA uplift phase
- a host cleanup phase
- a boundary-reopening phase

It should stay tightly scoped to proactive continuity quality under reset.

## Four stricter filters this phase must enforce

1. Event-frame restoration filter.
   - A proactive continuation answer is not good enough if it only recalls details.
   - It must also restore the larger event / plan frame without user nudging.

2. No-detour proactive filter.
   - If the memory packet already contains enough truth to continue, the answer must not
     fall back to:
     - “remind me what we were doing”
     - opportunistic browsing
     - tool-seeking
     - or menu/web lookup as the first move

3. Selective-recall filter.
   - A proactive continuation answer must not dump every remembered fragment back at the user.
   - It should bring back only the smallest useful set of:
     - event frame
     - active constraints
     - next-step-relevant details
   - More recall is not automatically better if it wastes tokens or clutters the answer.

4. Whole-path diagnosis filter.
   - This phase must not assume the memory kernel is the only place where proactive quality lives.
   - Diagnosis must explicitly consider:
     - memory supply
     - routing / policy
     - answer synthesis
     - response packaging
     - detour behavior

These are not extra features.

They are stricter pass/fail gates on the remaining proactive weakness.

## Project guardrails with refreshed emphasis

- donor-first
  - prefer tightening the existing continuity/synthesis seam over inventing a new subsystem
- modularity / upstream updateability
  - keep the fix bounded and local to the proven seam
- truth-first
  - if the stricter filters still fail, say so clearly
- fail-closed on the owned axis
  - do not reopen shadow memory paths while chasing proactive quality
- no benchmaxing
  - this is about product behavior after reset, not benchmark-shaped optimization
- no overengineering
  - do not turn one intermittent residual into a platform rewrite

## Ideal outcome

The ideal outcome is:

- proactive continuity becomes stably good under the stricter filters
- the answer restores the plan frame, not just fragments
- the system continues helpfully without pushing the user to restate what is already known
- the answer stays selective instead of token-wasteful or over-eager
- the fix remains thin, local, and maintainable

## End-state invariants

1. Boundary invariant.
   - Phase 22’s Brainstack/native coexistence decision remains intact.

2. Correctness invariant.
   - Phase 24’s profile-isolation reading remains intact.

3. Robustness invariant.
   - proactive continuity must pass under stricter filters, not just weakly acceptable phrasing.

4. No-detour invariant.
   - sufficient memory support must not degrade into unnecessary re-asking or first-move tool detours.

5. Selective-packaging invariant.
   - proactive help must stay concise and relevant instead of replaying excessive context.

6. Maintenance invariant.
   - the fix must stay bounded enough to remain headache-free later.
