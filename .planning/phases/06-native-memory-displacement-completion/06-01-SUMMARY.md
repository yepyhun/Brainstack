---
phase: 06-native-memory-displacement-completion
plan: 01
subsystem: host-runtime
tags: [hermes, brainstack, native-memory-displacement, host-patch, compatibility]
requires:
  - 01-brainstack-composite-provider-foundation
  - 05-orchestrator-working-memory-control-plane
provides:
  - GSD-compliant Phase 6 execution plan
  - Explicit native live-path displacement for built-in memory
  - Host-level regression tests for tool-surface and prompt-path cleanup
affects: [rtk-early-sidecar-integration, my-brain-is-full-crew-early-integration-surface]
tech-stack:
  added: [host-guardrails]
  patterns: [fail-closed-memory-tool, tool-surface-cleanup, minimal-host-patch]
key-files:
  created:
    - .planning/phases/06-native-memory-displacement-completion/06-01-PLAN.md
    - .planning/phases/06-native-memory-displacement-completion/06-01-SUMMARY.md
    - tests/run_agent/test_brainstack_native_memory_displacement.py
  modified:
    - .planning/STATE.md
    - run_agent.py
key-decisions:
  - "If the built-in memory store is inactive, Hermes must not expose the built-in memory tool on the live tool surface."
  - "Native memory review, flush, and prompt guidance must fail closed instead of staying half-wired."
  - "The host patch stays narrow: it cleans the live path but does not broaden the Hermes fork."
patterns-established:
  - "Tool-surface cleanup is tied to actual store availability, not only config intent."
  - "Direct built-in memory invocations return a clear disabled response instead of mutating state ambiguously."
  - "Background review inherits the same built-in memory live-path state as the main agent."
requirements-completed: [R5, R6, R7, A1, A2, A3, A4]
duration: 35min
completed: 2026-04-10
---

# Phase 06-01 Summary

**Phase 6 now fully displaces Hermes' native built-in memory live path for the Brainstack flow with a minimal host patch and passing host-level tests**

## Performance

- **Duration:** 35 min
- **Completed:** 2026-04-10
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Converted the freeform Phase 6 note into a canonical `06-01-PLAN.md` and preserved the original note as `06-LEGACY-PLAN-NOTES.md` so GSD indexing stays clean.
- Added explicit host-side helpers in `run_agent.py` to decide whether the built-in memory live path is actually active.
- Removed the built-in `memory` tool from the live tool surface whenever Hermes has no active built-in memory store.
- Kept built-in memory guidance, flush behavior, and memory-review nudges off when the native path is displaced.
- Made direct calls into the built-in `memory` branch fail closed with a clear disabled response instead of silently half-working.
- Ensured background review agents inherit the same built-in-memory displacement state as the primary agent.
- Added focused host-level regression tests and verified both the new Phase 6 test file and the existing Brainstack E2E suite:
  - `uv run --extra dev python -m pytest tests/run_agent/test_brainstack_native_memory_displacement.py -q`
  - `uv run --extra dev python -m pytest tests/agent/test_memory_plugin_e2e.py -q`

## Task Commits

No git commit was created during this inline execution pass. The executed phase artifacts remain in the working tree for review or later commit.

## Files Created/Modified

- `.planning/phases/06-native-memory-displacement-completion/06-01-PLAN.md` - canonical GSD execute plan for Phase 6
- `.planning/phases/06-native-memory-displacement-completion/06-01-SUMMARY.md` - execution summary for the completed Phase 6 plan
- `.planning/phases/06-native-memory-displacement-completion/06-LEGACY-PLAN-NOTES.md` - preserved original freeform notes without confusing GSD indexing
- `run_agent.py` - minimal host-side native memory displacement helpers and fail-closed guards
- `tests/run_agent/test_brainstack_native_memory_displacement.py` - host-level displacement regression coverage
- `.planning/STATE.md` - moved project state to Phase 6 verification

## Decisions Made

- Native built-in memory is considered active only when a real built-in memory store exists.
- Tool-surface cleanup is the authoritative displacement seam; the model should never see a built-in memory tool that cannot actually work.
- The host patch stays intentionally narrow and update-friendly rather than turning Phase 6 into a broad runtime rewrite.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The old `06-PLAN.md` would have repeated the same parser/index ambiguity fixed in earlier phases**
- **Found during:** Task 1 (Normalize Phase 6 into a GSD-executable plan and freeze the displacement boundary)
- **Issue:** The phase only had a freeform note, which would have kept official execute/verify tooling on a brittle path.
- **Fix:** Preserved the note as `06-LEGACY-PLAN-NOTES.md` and created `06-01-PLAN.md` as the single canonical executable artifact.
- **Verification:** `node /home/lauratom/.codex/get-shit-done/bin/gsd-tools.cjs verify plan-structure .planning/phases/06-native-memory-displacement-completion/06-01-PLAN.md` returned `valid: true`
- **Committed in:** not committed in this session

**2. [Rule 2 - Missing Critical] The built-in memory tool could remain visible even when no built-in store existed**
- **Found during:** Task 2/3 (host patch plus tests)
- **Issue:** Hermes could still surface the native `memory` tool and related guidance even when built-in memory was functionally off, which left a half-wired live path.
- **Fix:** Added explicit live-path helpers, removed the tool from the surface when the built-in store is absent, and made any stray direct invocation fail closed.
- **Verification:** `uv run --extra dev python -m pytest tests/run_agent/test_brainstack_native_memory_displacement.py -q` passed with the new displacement assertions
- **Committed in:** not committed in this session

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing critical)
**Impact on plan:** Both fixes were necessary to make Phase 6 officially executable and to ensure native displacement is real rather than cosmetic.

## Issues Encountered

- None blocking after the host patch centralized the displacement rule.

## User Setup Required

None for verification of this phase slice beyond keeping Hermes configured with the Brainstack provider and native memory/profile flags off.

## Next Phase Readiness

- Phase 6 is ready for `/gsd-verify-work 6`
- If verification passes, the next official build step is `/gsd-execute-phase 7 --interactive`

---
*Phase: 06-native-memory-displacement-completion*
*Completed: 2026-04-10*
