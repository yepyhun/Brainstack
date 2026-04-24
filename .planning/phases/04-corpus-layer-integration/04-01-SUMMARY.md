---
phase: 04-corpus-layer-integration
plan: 01
subsystem: memory
tags: [hermes, brainstack, corpus, sections, packing, recall]
requires:
  - 01-brainstack-composite-provider-foundation
  - 02-continuity-layer-integration
  - 03-graph-truth-layer-integration
provides:
  - GSD-compliant Phase 4 execution plan for corpus work
  - Local Brainstack corpus substrate
  - Explicit corpus ingestion and bounded section-aware recall on top of verified profile/continuity/graph shelves
affects: [orchestrator-working-memory-control-plane, native-memory-displacement-completion, rtk-early-sidecar-integration]
tech-stack:
  added: [sqlite, fts5]
  patterns: [explicit-corpus-owner, section-aware-packing, bounded-corpus-recall]
key-files:
  created:
    - .planning/phases/04-corpus-layer-integration/04-01-PLAN.md
    - .planning/phases/04-corpus-layer-integration/04-01-SUMMARY.md
    - plugins/memory/brainstack/corpus.py
  modified:
    - .planning/STATE.md
    - plugins/memory/brainstack/__init__.py
    - plugins/memory/brainstack/db.py
    - plugins/memory/brainstack/retrieval.py
    - plugins/memory/brainstack/plugin.yaml
    - tests/agent/test_memory_plugin_e2e.py
key-decisions:
  - "Corpus stays inside Brainstack as the canonical document/section shelf, not as a second provider or tool-facing memory surface."
  - "Corpus ingestion is explicit and bounded instead of silently mining every turn into long-form document memory."
  - "Corpus recall is section-aware and char-budgeted so it can help token efficiency instead of exploding the prompt."
patterns-established:
  - "Profile, continuity, graph truth, and corpus each keep a separate storage and retrieval path inside one provider."
  - "Corpus documents are broken into reusable sections with headings and token estimates."
  - "Query-time recall can merge profile, continuity, graph-truth, and corpus matches without collapsing ownership."
requirements-completed: [R1, R4, R5, R6, R7, A1, A2, A3, A4]
duration: 45min
completed: 2026-04-10
---

# Phase 04-01 Summary

**Brainstack Phase 4 is now a real corpus substrate with explicit document ingestion, section-aware recall, bounded packing, and passing targeted tests**

## Performance

- **Duration:** 45 min
- **Completed:** 2026-04-10
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments

- Converted the freeform Phase 4 notes into a real `04-01-PLAN.md` so GSD execute semantics no longer collide with an unstructured `04-PLAN.md`.
- Added a corpus slice to Brainstack with document and section tables plus FTS-backed recall.
- Added a dedicated `corpus.py` helper for stable document keys and section chunking.
- Wired explicit corpus ingestion into the Brainstack provider without adding model-facing tools.
- Extended recall so section-aware corpus snippets can surface alongside profile, continuity, and graph-truth context under a bounded character budget.
- Added targeted Phase 4 tests for corpus ingestion, section recall, and shelf separation, then verified the full plugin E2E file with `uv run --extra dev python -m pytest tests/agent/test_memory_plugin_e2e.py -q`.

## Task Commits

No git commit was created during this inline execution pass. The executed phase artifacts remain in the working tree for review or later commit.

## Files Created/Modified

- `.planning/phases/04-corpus-layer-integration/04-01-PLAN.md` - canonical GSD execute plan for Phase 4
- `.planning/phases/04-corpus-layer-integration/04-01-SUMMARY.md` - execution summary for the completed Phase 4 plan
- `.planning/phases/04-corpus-layer-integration/04-LEGACY-PLAN-NOTES.md` - preserved original freeform notes without confusing GSD indexing
- `plugins/memory/brainstack/corpus.py` - corpus document keying and section chunking helpers
- `plugins/memory/brainstack/db.py` - corpus document/section persistence plus FTS-backed search
- `plugins/memory/brainstack/__init__.py` - provider integration of explicit corpus ingestion and recall config
- `plugins/memory/brainstack/retrieval.py` - bounded corpus recall rendering
- `plugins/memory/brainstack/plugin.yaml` - updated Brainstack plugin description
- `tests/agent/test_memory_plugin_e2e.py` - Brainstack corpus ingestion, recall, and shelf separation tests
- `.planning/STATE.md` - moved project state to Phase 4 verification

## Decisions Made

- Corpus is canonical for document and section memory, but profile remains canonical for durable personal facts, continuity remains canonical for work recency, and graph truth remains canonical for temporal state and relations.
- Corpus ingestion is explicit through provider code, not silent auto-mining from normal turns.
- Corpus recall is packed by section and bounded by a character budget so it can cooperate with later control-plane token discipline.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The old `04-PLAN.md` would have confused official phase execution**
- **Found during:** Task 1 (Normalize Phase 4 into a GSD-executable plan and freeze corpus ownership boundaries)
- **Issue:** The freeform `04-PLAN.md` was not a canonical GSD execute artifact and would have repeated the same parser/index confusion already seen in Phase 3.
- **Fix:** Preserved the old notes as `04-LEGACY-PLAN-NOTES.md` and promoted `04-01-PLAN.md` to the single canonical executable artifact.
- **Verification:** `node /home/lauratom/.codex/get-shit-done/bin/gsd-tools.cjs verify plan-structure .planning/phases/04-corpus-layer-integration/04-01-PLAN.md` returned `valid: true`
- **Committed in:** not committed in this session

**2. [Rule 2 - Missing Critical] Graph and corpus fallback matching were too brittle for mixed queries**
- **Found during:** Task 2/3 (implementation plus tests)
- **Issue:** Multi-token mixed queries could match profile and continuity but miss graph-truth fallback because the graph search treated the full query string as one `LIKE` fragment.
- **Fix:** Switched graph and corpus fallback matching to token-based partial matching instead of single-string matching.
- **Verification:** `uv run --extra dev python -m pytest tests/agent/test_memory_plugin_e2e.py -q` passed with the new mixed-shelf corpus test included
- **Committed in:** not committed in this session

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing critical)
**Impact on plan:** Both fixes were necessary to make Phase 4 executable and to keep mixed-shelf recall realistic instead of paper-correct only.

## Issues Encountered

- The Phase 4 legacy notes were too skeletal to execute directly, so the first required action was normalizing them into a canonical plan.

## User Setup Required

None for verification of this phase slice. A future live-traffic activation step will still need Hermes config to point `memory.provider` at `brainstack`.

## Next Phase Readiness

- Phase 4 is ready for `/gsd-verify-work 4`
- If verification passes, the next official build step is `/gsd-execute-phase 5 --interactive`

---
*Phase: 04-corpus-layer-integration*
*Completed: 2026-04-10*
