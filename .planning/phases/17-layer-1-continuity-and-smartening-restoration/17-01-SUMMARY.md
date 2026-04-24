# Phase 17 Summary

## Outcome

Phase 17 removed the old handwritten Tier-1 path from the center of Brainstack Layer 1 and replaced it with a bounded executive retrieval shape that matches the donor-first recovery contract more closely.

The phase stayed disciplined:

- no new multilingual heuristics
- no fake semantic stand-in
- no L2 or L3 backend migration hidden inside the L1 rewrite
- no mandatory live rebuild during execution

Instead, the phase established a new L1 center:

- a dedicated executive retrieval module now fuses:
  - keyword / FTS evidence
  - graph evidence
  - temporal evidence
  - an explicit semantic channel status
- the semantic leg is now documented as degraded-by-design until donor-backed vector retrieval lands, instead of silently pretending FTS is “semantic enough”
- the live ingest path no longer turns handwritten Tier-1 profile guesses into durable profile rows
- `control_plane.py` now treats L1 as executive retrieval intelligence instead of as another place to grow local scoring glue

## Source Changes

- added `brainstack/executive_retrieval.py`
  - explicit channel contract
  - channel metadata
  - reciprocal-rank-fusion style selection
  - explicit degraded semantic channel handling
- rewired `brainstack/control_plane.py`
  - working-memory construction now flows through executive retrieval
  - channel coverage is surfaced directly instead of relying on heuristic Tier-1 centrality
- thinned `brainstack/extraction_pipeline.py`
  - live Tier-1 ingest plans now leave `profile_candidates` empty
- thinned `brainstack/__init__.py`
  - normal `sync_turn()` and `on_session_end()` no longer convert Tier-1 heuristic matches into durable profile rows
- added bounded Phase 17 eval tooling:
  - `scripts/run_brainstack_phase17_eval_ladder.py`
  - `scripts/run_brainstack_longmemeval_subset.py`
- added or updated focused coverage in:
  - `tests/test_brainstack_executive_retrieval.py`
  - `tests/test_brainstack_real_world_flows.py`
  - `tests/test_brainstack_usefulness.py`
  - `tests/test_brainstack_retrieval_contract.py`
- ignored generated LongMemEval reports in `.gitignore`

## Validation

### Source-side validation

- targeted Phase 17 test set passes:
  - `30 passed in 1.58s`
- the bounded eval ladder now proves the fast gates directly:
  - Gate A: `4 passed in 0.03s`
  - Gate B: `26 passed in 3.35s`
  - Gate C: explicit skip if `COMET_API_KEY` / `COMETAPI_API_KEY` is absent
- this coverage proves:
  - the semantic leg is explicit and degraded, not silently missing
  - the old Tier-1 heuristic path no longer writes durable profile rows in the normal path
  - same-session style recall now surfaces through continuity/recent evidence instead of heuristic profile promotion
  - telemetry and retrieval-contract expectations still hold after the L1 rewrite

### Installer / runtime carry-through

- integration-kit doctor dry-run passes against the Bestie checkout
- integration-kit real install passes against the Bestie checkout
- no live rebuild was forced during execution; per current workflow rules, rebuild remains reserved for explicit test gates

## Result

Phase 17 is now in a materially better state than the pre-restoration L1:

- the old handwritten Tier-1 path is no longer the effective center of L1 behavior
- L1 now has a real executive retrieval module and channel contract
- the semantic gap is explicit instead of being hidden behind fake local glue
- the repo now includes a bounded eval ladder for repeated Phase 17 checks without mandatory rebuilds

This does **not** mean the full Hindsight-strength restoration is finished. The major remaining gap is the donor-backed semantic leg, which depends on the embedded-backend recovery path planned for later phases.

## Follow-up

- Phase 17 verify should use the new bounded eval ladder first, and only trigger a live rebuild if a runtime smoke is actually needed
- Phase 18 remains the next architectural recovery step
