# Phase 36 Implementation Contract

## invariant

Brainstack must render a quieter, deduplicated, owner-driven working-memory packet without regressing exact recall, durable truth, or fail-closed honesty.

## required implementation properties

- the final working-memory packet must be assembled through explicit owner arbitration rather than broad section concatenation
- the implementation must treat system substrate plus working-memory rendering as one combined packet-quality surface
- the implementation must reduce overlapping render surfaces for the same underlying truth
- continuity, recent continuity, and transcript must not routinely coexist as near-duplicate retellings for ordinary turns
- profile, graph, and operating truth must not restate the same fact multiple times unless:
  - they disagree in a meaningful way
  - or the temporal distinction is itself relevant truth
- the same underlying truth must not appear once as substrate guidance and again as evidence render unless that second appearance adds a distinct owner or conflict role
- wrapper framing must be singular and truthful:
  - one memory boundary
  - no layered quasi-system-note inflation
- operating truth must outrank continuity-derived fallback where an explicit committed operating record exists
- exact canonical contract recall must remain available and exact
- ordinary-turn invariant support must remain narrow
- token savings must come from lower duplication and better arbitration, not from hiding evidence or silently dropping truth
- the result must remain donor-first, upstream-friendly, and free of new heuristic farms

## prohibited outcomes

- new packet-shape cue farms
- user-specific or test-specific dedupe rules
- multiple memory wrapper notes surviving “for clarity”
- collapsing away conflicts, supersession, or provenance-relevant distinctions
- shrinking the packet by making the system less truthful
- reintroducing broad behavior governance under a new rendering label

## likely implementation seams

- `brainstack/retrieval.py`
- `brainstack/control_plane.py`
- `brainstack/executive_retrieval.py`
- `brainstack/operating_context.py`
- `brainstack/behavior_policy.py`
- `brainstack/output_contract.py` only if needed for packet-boundary consistency
- `agent/memory_manager.py`
- `scripts/install_into_hermes.py`
- only the minimal `hermes-final` host seams needed to keep the packet shape singular and parity-safe at runtime

## verify contract

- prove the new packet shape has fewer sections or less duplicate content on representative turns
- prove packet-quality at the combined hot-path level with concrete metrics:
  - section count
  - combined character footprint
  - repeated semantic-key count
  - cross-surface duplicate count
- prove exact canonical contract recall still returns the correct source truth
- prove committed operating truth replaces continuity fallback in the packet where appropriate
- prove continuity/transcript collapse does not erase needed supporting evidence
- prove the host/runtime no longer adds a second competing memory-authority wrapper
- prove no new heuristic farm was introduced to fake the result
- prove parity on:
  - source
  - `hermes-final`
  - rebuilt live runtime

## canonical principle reference

- [IMMUTABLE-PRINCIPLES.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md)

## recommended model level

- `xhigh`
