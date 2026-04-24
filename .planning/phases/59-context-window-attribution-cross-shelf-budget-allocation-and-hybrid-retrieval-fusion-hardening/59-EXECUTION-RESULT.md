# Phase 59 Execution Result

## Status

- context-window attribution: complete
- source-of-truth allocator/fusion work: complete
- install proof on `finafina`: complete
- targeted validation: complete

## Edited source-of-truth files

- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/__init__.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/control_plane.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/executive_retrieval.py`

## What changed

1. Context-window attribution is now explicit instead of blame-first.
   - the current live Hermes stack was re-measured before changing Brainstack
   - the large host prompt surfaces remain a major part of context pressure:
     - `MEMORY_GUIDANCE ~4597 char`
     - `USER_PROFILE_GUIDANCE ~3248 char`
     - `TOOL_USE_ENFORCEMENT_GUIDANCE ~1419 char`
     - `OPENAI_MODEL_EXECUTION_GUIDANCE ~3176 char` when active
     - live `USER.md ~790 char`
   - the accepted result is:
     - Brainstack is a real contributor
     - but the complaint is not truthfully attributable to Brainstack alone

2. Brainstack now has a real shared evidence allocator.
   - `WorkingMemoryPolicy` now carries `evidence_item_budget`
   - the control plane sets route-aware shared caps instead of only per-shelf caps
   - executive retrieval now selects evidence rows under:
     - per-shelf hard caps
     - one shared cross-shelf evidence budget
   - this improves boundedness without deleting whole shelves or adding query-specific hacks

3. Hybrid retrieval fusion is now less transcript-biased and more agreement-aware.
   - channel fusion is now weighted instead of using flat RRF contribution for every channel/shelf pair
   - multi-channel agreement now gets an explicit bonus
   - transcript-only preference in tie-breaking was reduced so multi-signal items can win when they should

## Installed-runtime proof summary

- source-of-truth installer ran successfully against `/home/lauratom/Asztal/ai/finafina`
- runtime rebuilt and returned `running; connected=discord`
- doctor passed in docker mode after install
- running container now includes:
  - `evidence_item_budget`
  - `FUSION_CHANNEL_WEIGHTS`
  - `shared_budget_enabled`

## Targeted validation

### Live attribution proof

- the current Bestie runtime still shows a large host-side prompt stack before Brainstack packetization
- live-adjacent prefetch checks on the installed runtime showed:
  - Brainstack selected only `3-5` evidence rows for the tested queries
  - this supports the attribution verdict that fast context fill is not primarily caused by oversized Brainstack packets alone

### Synthetic retrieval proof

- weighted fusion proof on the installed code path:
  - a multi-channel continuity candidate (`keyword + semantic`) now outranks a transcript keyword-only candidate
- shared allocator proof on the installed code path:
  - with `evidence_item_budget = 3`, total selected evidence rows were capped at `3`
  - with `evidence_item_budget = 5`, the same ranked candidate set expanded to `5`

### Hygiene / compile proof

- touched source files `py_compile`: pass
- source-of-truth `git diff --check`: pass
- docker-mode doctor on `finafina`: pass

## Truth-first verdict

- Phase 59 closes as a quality/efficiency phase, not a capability phase
- the main user complaint was investigated honestly before changing Brainstack
- the Brainstack-owned correction now exists:
  - shared cross-shelf evidence budgeting
  - stronger hybrid fusion
- the result improves boundedness and ranking quality without:
  - donor churn
  - backend-swap theater
  - heuristic farms
  - fake token wins by blind evidence deletion
