# Phase 46 Context

## problem statement

Phase 41 showed a gap between “many tests exist” and “the strict inspector will trust the system.” The main issue is that the biggest hubs and ugliest fallback/authority seams still lean too much on indirect or mock-heavy proof.

## why this phase exists

- after cleanup and decomposition, the project needs hard evidence, not just confidence
- inspector-grade quality requires direct proof on the seams most likely to be challenged

## findings this phase is intended to close

- Phase 41 Batch 5:
  - 14. The proof surface is broad, but major hubs still have direct-coverage debt
  - residual proof concerns connected to 9 and 16

## architectural posture

- prefer deterministic replay and evidence over benchmark cosmetics
- target the real hotspots first

## canonical principle reference

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`

## recommended model level

- `xhigh`
