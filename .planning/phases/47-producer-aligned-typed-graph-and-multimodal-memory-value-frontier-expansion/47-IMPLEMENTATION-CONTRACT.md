# Phase 47 Implementation Contract

## invariant

This phase must increase product value without undoing the anti-heuristic cleanup achieved in earlier phases.

## canonical principle reference

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`
- pinned names:
  - `Donor-first`
  - `Modularity / Upstream updateability`
  - `No benchmaxing`
  - `Truth-first / no "good enough"`
  - `Zero heuristic sprawl`
  - `Multimodal-first architecture`

## required properties

- all new graph or multimodal value must come from typed, producer-aligned evidence paths
- no raw-text graph widening in the live path
- multimodal expansion must remain architecture-native, not bolt-on prompt glue
- proof must show value uplift and no heuristic regression

## prohibited outcomes

- resurrecting legacy text extraction because it is faster
- introducing modality-specific hacks that trap the system in text-only assumptions
- inflating stored data without clear retrieval value

## required verification artifact

- proof that value increased through typed producer inputs while the heuristic boundary stayed closed

## recommended model level

- `xhigh`
