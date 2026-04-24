# Phase 44 Implementation Contract

## invariant

This phase must reduce ambiguity by shrinking compatibility surfaces, not by layering more migration glue on top of them.

## canonical principle reference

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`
- pinned names:
  - `Donor-first`
  - `Fail-closed upstream compatibility`
  - `Truth-first / no "good enough"`
  - `Zero heuristic sprawl`
  - `Multimodal-first architecture`

## required properties

- each retired or quarantined legacy path must have:
  - an explicit replacement path
  - tests or proof for the canonical path
  - clear status if full retirement is not yet possible
- no silent fallback back into legacy storage or shared config where canonical scoped state exists

## prohibited outcomes

- keeping old and new paths both active because that is easier
- hiding migration incompleteness behind comments only
- reintroducing text-heuristic graph logic into the live path

## required verification artifact

- verification notes proving which legacy paths were retired, which were quarantined, and which remain intentionally bounded

## recommended model level

- `xhigh`
