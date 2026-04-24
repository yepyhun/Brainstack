---
phase: 05-orchestrator-working-memory-control-plane
plan: 01
subsystem: memory
tags: [hermes, brainstack, working-memory, control-plane, provenance, token-efficiency]
requires:
  - 02-continuity-layer-integration
  - 03-graph-truth-layer-integration
  - 04-corpus-layer-integration
provides:
  - GSD-compliant Phase 5 execution plan for control-plane work
  - Local Brainstack working-memory control-plane slice
  - Explicit policy-driven recall, provenance escalation, and bounded tool-avoidance behavior
affects: [native-memory-displacement-completion, rtk-early-sidecar-integration, my-brain-is-full-crew-early-integration-surface]
tech-stack:
  added: [policy-composition]
  patterns: [query-analysis, bounded-working-memory, provenance-escalation, explicit-tool-avoidance]
key-files:
  created:
    - .planning/phases/05-orchestrator-working-memory-control-plane/05-01-PLAN.md
    - .planning/phases/05-orchestrator-working-memory-control-plane/05-01-SUMMARY.md
    - plugins/memory/brainstack/control_plane.py
  modified:
    - .planning/STATE.md
    - plugins/memory/brainstack/__init__.py
    - plugins/memory/brainstack/db.py
    - plugins/memory/brainstack/retrieval.py
    - tests/agent/test_memory_plugin_e2e.py
key-decisions:
  - "The control plane is orchestration-only; canonical ownership remains with the existing profile, continuity, graph-truth, and corpus shelves."
  - "High-stakes queries and open conflicts automatically escalate provenance depth and disable memory-only tool avoidance."
  - "Low-stakes preference-style queries stay compact and can avoid unnecessary corpus injection."
patterns-established:
  - "Query analysis drives bounded per-shelf budgets instead of static prefetch limits alone."
  - "Working-memory policy is explicit and testable rather than hidden in ad hoc retrieval code."
  - "Mixed-shelf recall can stay compact for normal questions and become more explicit only when the case demands it."
requirements-completed: [R4, R5, R6, R7, A1, A2, A3, A4]
duration: 50min
completed: 2026-04-10
---

# Phase 05-01 Summary

**Brainstack Phase 5 is now a real working-memory control plane with explicit policy, provenance escalation, bounded tool avoidance, and passing targeted tests**

## Performance

- **Duration:** 50 min
- **Completed:** 2026-04-10
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Converted the freeform Phase 5 notes into a real `05-01-PLAN.md` so GSD execute semantics no longer collide with an unstructured `05-PLAN.md`.
- Added a dedicated `control_plane.py` slice that performs query analysis and chooses compact vs deep working-memory behavior.
- Rewired Brainstack prefetch through the new control plane instead of relying on fixed static shelf limits only.
- Added explicit policy outputs for confidence band, provenance mode, conflict escalation, and tool-avoidance allowance.
- Extended retrieval rendering so provenance can expand when stakes or conflicts require it without spamming every normal query.
- Extended graph search rows to carry source metadata needed for explicit provenance on conflict/current-state cases.
- Added targeted Phase 5 tests for compact low-stakes behavior, escalated high-stakes provenance, and conflict-driven tool-avoidance escalation, then verified the full plugin E2E file with `uv run --extra dev python -m pytest tests/agent/test_memory_plugin_e2e.py -q`.

## Task Commits

No git commit was created during this inline execution pass. The executed phase artifacts remain in the working tree for review or later commit.

## Files Created/Modified

- `.planning/phases/05-orchestrator-working-memory-control-plane/05-01-PLAN.md` - canonical GSD execute plan for Phase 5
- `.planning/phases/05-orchestrator-working-memory-control-plane/05-01-SUMMARY.md` - execution summary for the completed Phase 5 plan
- `.planning/phases/05-orchestrator-working-memory-control-plane/05-LEGACY-PLAN-NOTES.md` - preserved original freeform notes without confusing GSD indexing
- `plugins/memory/brainstack/control_plane.py` - query analysis and working-memory policy orchestration
- `plugins/memory/brainstack/__init__.py` - provider integration of the control-plane prefetch path
- `plugins/memory/brainstack/db.py` - graph search provenance fields for escalated rendering
- `plugins/memory/brainstack/retrieval.py` - policy-aware working-memory rendering
- `tests/agent/test_memory_plugin_e2e.py` - Brainstack control-plane behavior tests
- `.planning/STATE.md` - moved project state to Phase 5 verification

## Decisions Made

- The control plane is not a new shelf; it only allocates attention and budget across the existing shelves.
- Memory-only behavior is allowed only when support is strong enough and no high-stakes/conflict escalation blocks it.
- Provenance stays compact by default and expands only when the situation actually demands it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The old `05-PLAN.md` would have confused official phase execution**
- **Found during:** Task 1 (Normalize Phase 5 into a GSD-executable plan and freeze control-plane boundaries)
- **Issue:** The freeform `05-PLAN.md` was not a canonical GSD execute artifact and would have repeated the same parser/index confusion already fixed in earlier phases.
- **Fix:** Preserved the old notes as `05-LEGACY-PLAN-NOTES.md` and promoted `05-01-PLAN.md` to the single canonical executable artifact.
- **Verification:** `node /home/lauratom/.codex/get-shit-done/bin/gsd-tools.cjs verify plan-structure .planning/phases/05-orchestrator-working-memory-control-plane/05-01-PLAN.md` returned `valid: true`
- **Committed in:** not committed in this session

**2. [Rule 2 - Missing Critical] Static prefetch limits could not satisfy Phase 5 control-plane promises**
- **Found during:** Task 2/3 (implementation plus tests)
- **Issue:** The prefetch path still relied on fixed shelf limits and had no explicit code-facing notion of stakes, confidence, provenance depth, or tool-avoidance policy.
- **Fix:** Added a dedicated working-memory control plane that analyzes the query, allocates per-shelf budgets, escalates provenance when needed, and exposes explicit tool-avoidance decisions.
- **Verification:** `uv run --extra dev python -m pytest tests/agent/test_memory_plugin_e2e.py -q` passed with the new control-plane tests included
- **Committed in:** not committed in this session

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing critical)
**Impact on plan:** Both fixes were necessary to make Phase 5 executable and to ensure the control plane is a real orchestration layer rather than roadmap-only language.

## Issues Encountered

- None blocking after the control-plane slice replaced the static prefetch path.

## User Setup Required

None for verification of this phase slice. A future live-traffic activation step will still need Hermes config to point `memory.provider` at `brainstack`.

## Next Phase Readiness

- Phase 5 is ready for `/gsd-verify-work 5`
- If verification passes, the next official build step is `/gsd-execute-phase 6 --interactive`

---
*Phase: 05-orchestrator-working-memory-control-plane*
*Completed: 2026-04-10*
