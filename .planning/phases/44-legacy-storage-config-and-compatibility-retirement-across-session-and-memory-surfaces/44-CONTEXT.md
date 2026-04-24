# Phase 44 Context

## problem statement

Phase 41 proved that the product still carries several old compatibility surfaces:

- session transcript SQLite + legacy JSONL duality
- hindsight legacy shared config loading
- provider/config alias and fallback compatibility paths
- legacy graph extractor debt still present in-repo

These are understandable transitional seams, but they expand ambiguity and maintenance cost.

## why this phase exists

- masterpiece-grade systems should not rely on indefinite coexistence of old and new paths
- strict inspection will question whether the product really has one canonical runtime path per concern

## findings this phase is intended to close

- Phase 41 Batch 4:
  - 12. Session and memory subsystems still carry legacy dual-storage compatibility debt
  - 13. Legacy graph extractor still exists as compatibility debt even after live ingest was hardened
- Phase 41 Batch 5:
  - 15. Single-file and isolated-node patterns suggest hidden maintainability islands
    where legacy fragments may still be contributing

## architectural posture

- prefer retirement or quarantine over indefinite dual-mode support
- do not replace retired legacy with another compatibility maze

## canonical principle reference

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`

## recommended model level

- `xhigh`
