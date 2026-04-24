# Phase 45 Context

## problem statement

Phase 41 proved the repo still has:

- very large orchestration functions
- high-betweenness bridge nodes
- high cross-community coupling
- hotspot files where change blast radius is too high for comfortable inspection

Even if the product works, this remains a serious maintainability and review liability.

## why this phase exists

- the strict inspector will not accept “but it is tested” as a full answer to 3000-line and 1400-line orchestration hubs
- decomposition must happen after routing/runtime/compatibility cleanup so the refactor targets stable logic, not unstable seams

## findings this phase is intended to close

- Phase 41 Batch 3:
  - 7. Cross-community coupling is still very high
  - 8. Gateway/platform runtime is still bridge-node heavy
  - 9. There are still giant untested or weakly test-targeted hotspot functions
- Phase 41 Batch 5:
  - 15. Single-file and isolated-node patterns suggest hidden maintainability islands
  - 16. Large orchestration functions remain a systemic inspection liability even where tests exist

## architectural posture

- this phase is about real blast-radius reduction, not formatting
- every extraction must make upstream updateability easier or at least not harder

## canonical principle reference

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`

## recommended model level

- `xhigh`
