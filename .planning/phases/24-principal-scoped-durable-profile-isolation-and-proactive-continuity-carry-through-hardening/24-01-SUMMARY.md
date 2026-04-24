# Phase 24 Summary

## Outcome

Phase `24` is execution-complete.

The two Phase `23` residuals were real, but they did **not** share one lower seam:

- `cross_principal_profile_bleed`
  - root cause: durable personal profile rows were still globally keyed and some core reads were still global-by-`stable_key`
- `proactive_continuity_after_reset`
  - root cause: the carry-through miss was not a simple storage loss
  - the packet already carried the needed dietary evidence, but continuation-shaped queries were not getting strong enough continuation guidance / salience shaping

## Workstream A: principal-scoped durable profile isolation

Deeper truth:

- the bug was **not** just dropped metadata inside Tier-2 reconcile
- the deeper seam was:
  - personal `identity` / `preference` rows were effectively global durable rows
  - scoped reads were metadata-filtered too late
  - `_current_user_name(...)` still read identity rows globally

Repair:

- personal `identity` / `preference` rows now use principal-aware durable storage identity
- external/logical `stable_key` behavior stays stable at the API boundary
- scoped personal reads do **not** fall back to old global rows
- Tier-2 profile reconcile now receives the real scoped metadata payload
- scoped identity lookup now drives user alias canonicalization
- profile retrieval telemetry now records against the real durable storage row, not the global logical key only

Primary proof:

- [phase24-principal-bleed-canary.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase24/phase24-principal-bleed-canary.json)
  - `bleed_detected = false`

## Workstream B: proactive continuity carry-through hardening

Truth before patch:

- the dietary detail was **not** simply missing from memory
- deterministic packet inspection showed the transcript evidence was available
- the remaining weakness was in continuation-shaped salience / answer-shaping

Repair:

- added explicit continuation-query detection
- continuation-shaped queries now receive:
  - stronger continuity recent/match budget
  - stronger transcript budget
  - slightly stronger graph budget
  - bounded continuation guidance in the working-memory block
- the guidance is selective:
  - carry forward concrete recalled constraints and details
  - do not invent missing constraints

Primary proof:

- [phase24-carry-through-deterministic.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase24/phase24-carry-through-deterministic.json)
  - constrained case keeps `gluten-free`
  - negative control does **not** fabricate `gluten-free`
- [phase24-live-proactive-rerun.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase24/phase24-live-proactive-rerun.json)
  - focused deployed-path rerun: `passed = true`

## Shared-seam verdict

- `no`
- the two residuals were causally separate:
  - principal bleed = durable storage / scoped lookup correctness seam
  - carry-through = continuation salience / synthesis guidance seam

## Validation

Brainstack source:

- `pytest tests/test_brainstack_phase24_correctness.py tests/test_brainstack_phase21_memory_ownership.py -q`
  - `15 passed`
- `ruff check`
  - clean
- `mypy --follow-imports=silent`
  - clean

Bestie mirror / integration:

- `pytest tests/plugins/memory/test_brainstack_phase24_correctness.py tests/plugins/memory/test_brainstack_threading.py tests/run_agent/test_brainstack_only_mode.py tests/agent/test_memory_provider.py -q`
  - `62 passed`
- `ruff check`
  - clean
- `mypy --follow-imports=silent`
  - clean

## Files changed

Brainstack source:

- [db.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/db.py)
- [reconciler.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/reconciler.py)
- [control_plane.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/control_plane.py)
- [retrieval.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/retrieval.py)
- [test_brainstack_phase24_correctness.py](/home/lauratom/Asztal/ai/atado/Brainstack/tests/test_brainstack_phase24_correctness.py)

Bestie mirror:

- [db.py](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest/plugins/memory/brainstack/db.py)
- [reconciler.py](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest/plugins/memory/brainstack/reconciler.py)
- [control_plane.py](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest/plugins/memory/brainstack/control_plane.py)
- [retrieval.py](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest/plugins/memory/brainstack/retrieval.py)
- [test_brainstack_phase24_correctness.py](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest/tests/plugins/memory/test_brainstack_phase24_correctness.py)

## Final reading

Phase `24` did **not** solve these residuals with a ragtapasz patch.

It closed them at the deeper credible seams while preserving:

- donor-first
- modularity / upstream updateability
- truth-first
- fail-closed on the owned axis
- no benchmaxing
- no overengineering

## Recommended next step

- checkpoint Phase `24`
- then, if needed, refresh the broader deployed-live quality baseline on top of the new Phase `24` truth instead of opening another correction phase immediately
