# Phase 58 Context

## why this phase exists

Phases 56 and 57 closed important runtime correctness defects, and the `croniter` wizard hole is now fixed. But the project is still not cleanly inspector-ready because the remaining debt is no longer about feature correctness alone.

The remaining problem is a three-layer debt stack:

1. source-of-truth release debt
2. persistent-state hygiene residue
3. half-wired and legacy shipped surfaces that were partially demoted but not fully cleaned

This phase exists to close that stack without re-opening behavior-governor drift or inventing new capability scope.

## verified current findings

- source-of-truth repo is still dirty in:
  - `brainstack/__init__.py`
  - `brainstack/db.py`
  - `scripts/brainstack_doctor.py`
  - `scripts/install_into_hermes.py`
- installed runtime is better than before but not perfectly clean:
  - canonical `USER.md` is present
  - `compiled_behavior_policies = 0`
  - a legacy interrupt/status transcript row still exists in `brainstack.db`
  - a legacy superseded `behavior_contract` row still exists in `brainstack.db`
- planning corpus still carries stale or open-seeming wording from earlier phases
- automated structural audit strongly suggests large half-demoted surfaces remain in shipped source, even where they are no longer active runtime authority

## accepted diagnosis

- the remaining debt is not a new product capability gap
- it is not primarily a Discord UX question either
- it is inspector-readiness debt across:
  - repo cleanliness
  - persistent-state cleanliness
  - shipped-surface simplicity
  - planning/proof coherence

The risk is not that the runtime obviously breaks. The risk is that a strict reviewer finds:

- stale authority residue
- half-wired legacy layers
- dead compatibility surfaces
- stale planning claims
- dirty release boundaries

and concludes the project is still being held together by recovery residue.

## source-of-truth rule for this phase

- code source of truth:
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`
- install-and-proof target:
  - `/home/lauratom/Asztal/ai/finafina`

No cleanup counts unless it starts in `Brainstack-phase50` and is then reproduced onto `finafina`.

## proof stratification

This phase needs four proof layers:

1. source repo proof
   - clean worktree
   - releasable diff

2. install/runtime proof
   - doctor
   - tests
   - clean installed target

3. persistent-state proof
   - DB and profile state inspection
   - no stale contamination or contradictory authority residue

4. inspector-story proof
   - planning and execution artifacts say the same thing the runtime and repo actually show

## design guardrails

- do not trust automated dead-code results blindly; validate runtime entry roots before deletion
- treat stale persistent-state rows as real debt, not cosmetic leftovers
- if a compatibility shim remains, call it what it is and bound it tightly
- if a file is dead or effectively dead in shipped source, either remove it or justify it explicitly
- do not reopen Brainstack-governor logic to solve cleanliness problems

## anti-drift reminders

- this is not a return to feature building
- this is not a chance to add one more memory lane
- this is not a broad rewrite of retrieval or extraction
- this is not a prompt-tuning phase
- the correct result is a smaller, cleaner, more auditable source of truth
