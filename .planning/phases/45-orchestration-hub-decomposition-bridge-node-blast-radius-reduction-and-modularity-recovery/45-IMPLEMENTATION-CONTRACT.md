# Phase 45 Implementation Contract

## invariant

This phase must improve modularity and reduce blast radius in the real hotspots, not merely move code around.

## canonical principle reference

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`
- pinned names:
  - `Donor-first`
  - `Modularity / Upstream updateability`
  - `Truth-first / no "good enough"`
  - `Zero heuristic sprawl`
  - `Multimodal-first architecture`

## required properties

- every major extraction must have a clear responsibility boundary
- hub decomposition must preserve donor-first updateability
- graph-measured hotspots and bridges must be the primary targets, not aesthetic preferences
- proof must show behavior parity after decomposition

## prohibited outcomes

- splitting one giant function into several tightly coupled giant helpers
- moving complexity without reducing dependency concentration
- introducing local abstractions that make upstream sync harder while buying no structural improvement

## required verification artifact

- before/after hotspot and coupling notes tied back to the relevant Phase 41 findings

## recommended model level

- `xhigh`
