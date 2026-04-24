# Phase 23 Summary

## Outcome

Phase `23` is execution-complete at gate as a validation phase.

The broader deployed-live matrix, after correcting the harness to use the real deployed provider path, landed at `9 / 10` and showed that the post-Phase-22 product quality is broadly healthy without reopening the Brainstack/native boundary.

This phase also surfaced two honest residuals that should drive the next thread:

- one direct conversational miss:
  - proactive continuity after reset dropped the dietary carry-through
- one deeper architecture-quality bug:
  - style/name/language durable profile items appeared under unrelated principals

## What changed

### Phase 23 live-quality harness

- `scripts/run_brainstack_phase23_live_quality.py`
  - stages a temporary deployed-like `HERMES_HOME`
  - resolves provider/runtime settings through the real Hermes runtime-provider path instead of hand-assembling provider auth
  - runs a broader multi-scenario live matrix through `AIAgent.run_conversation(...)`
  - captures packet and persisted-scope evidence for anomaly classification

### Phase artifacts

- `reports/phase23/brainstack-23-scenario-matrix.json`
- `reports/phase23/brainstack-23-broader-deployed-live-eval.json`

## Broader live truth

### Overall result

- scenarios:
  - `10`
- passed:
  - `9`
- accuracy:
  - `0.9`

### By category

- coherent continuous conversation:
  - `2 / 2`
- stateful continuity after reset:
  - `2 / 2`
- proactive stateful continuity:
  - `0 / 1`
- long-range relation-tracking:
  - `4 / 4`
- larger knowledge-body use:
  - `1 / 1`

## Harness truth

The first live attempts in this phase were not product truth because the harness initially misread the deployed provider path.

What was corrected:

- the script no longer treats the staged config model dict as a model string
- the script no longer hand-builds provider auth from partial staged files
- the script now reuses Hermes runtime provider resolution against the staged temp home

This matters because the earlier `404` and `401` failures were harness/auth-path mistakes, not Brainstack product failures.

## Residual map

### 1. Proactive continuity miss

Classification:

- `product_bug`

Truth:

- the system remembered the event and venue after reset
- it did not carry forward the dietary constraint in the proactive continuation answer

### 2. Cross-principal durable profile bleed

Classification:

- `product_bug`

Truth:

- style/name/language profile items showed up under unrelated principal scopes later in the matrix
- the affected scenarios were:
  - `proactive_continuity_after_reset`
  - `temporal_order`
  - `aggregate_trip_distance`
  - `corrected_date_resolution`
  - `relation_tracking_pet_owner`
  - `larger_knowledge_body`

Why this matters:

- this is deeper than a single conversational miss
- it suggests principal-scoped durable profile isolation is not holding cleanly under the broader live path

## Validation

- Phase `23` live matrix:
  - `10` scenarios
  - `9` passed
- script quality gate:
  - `ruff` clean on `scripts/run_brainstack_phase23_live_quality.py`
  - `mypy --follow-imports=silent` clean on the same file

## Architectural reading

This phase does **not** justify reopening the Phase `22` boundary.

It supports the current model:

- Brainstack remains the durable personal-memory owner
- native coexistence points do not need broader rollback

The stronger new concern is not boundary confusion. It is principal-scope hygiene inside the durable profile path, plus a narrower continuity carry-through miss.

## Next step

- checkpoint Phase `23`
- then add + plan a follow-up phase focused on:
  - principal-scoped durable profile isolation
  - proactive continuity carry-through hardening
