# Phase 25 Summary

## Outcome

Phase `25` is execution-complete as a baseline-refresh validation phase.

The broader deployed-live score stayed at `9 / 10`, but the residual map became
cleaner than the old Phase `23` baseline:

- `cross_principal_profile_bleed` is resolved
- `larger_knowledge_body` improved from `acceptable_pass` to `strong_pass`
- the only remaining residual is `proactive_continuity_after_reset`

## What changed

### Phase 25 live-quality harness

- added:
  - [run_brainstack_phase25_live_quality.py](/home/lauratom/Asztal/ai/atado/Brainstack/scripts/run_brainstack_phase25_live_quality.py)
- purpose:
  - rerun the same broader live scenario family after Phase `24`
  - keep a clean Phase `25` artifact namespace
  - include explicit comparison against the old Phase `23` baseline

### Phase artifacts

- broader rerun report:
  - [brainstack-25-broader-deployed-live-eval.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase25/brainstack-25-broader-deployed-live-eval.json)
- scenario matrix:
  - [brainstack-25-scenario-matrix.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase25/brainstack-25-scenario-matrix.json)
- focused variance check:
  - [brainstack-25-proactive-variance-check.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase25/brainstack-25-proactive-variance-check.json)

## Refreshed broader live truth

### Overall result

- broader live matrix:
  - `9 / 10`
  - `0.9` accuracy

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
  - now `strong_pass`

## Baseline comparison against Phase 23

- accuracy delta:
  - `0.0`
- pass-count delta:
  - `0`
- resolved residuals:
  - `cross_principal_profile_bleed`
- persisting residuals:
  - `proactive_continuity_after_reset`
- new residuals:
  - none
- scenario deltas:
  - `larger_knowledge_body` improved from `acceptable_pass` to `strong_pass`

## Residual reading

### 1. Cross-principal profile bleed

- this did **not** reopen
- the broader rerun supports the Phase `24` reading that the durable
  profile-isolation seam is closed

### 2. Proactive continuity after reset

- this still missed once in the broader matrix
- the miss shape changed:
  - the answer kept `Riverside Kitchen`
  - and the `gluten-free` dietary constraint
  - but dropped the explicit event framing (`birthday dinner`)

### Focused variance read

- the focused proactive rerun check landed at:
  - `2 / 3` pass
  - `intermittent = true`
- reading:
  - this does **not** look like a clean Phase `24` seam reopen
  - it reads more like lingering live answer-synthesis / salience variance around
    proactive event carry-through

## Validation

- live baseline refresh:
  - broader deployed-live matrix rerun complete
- focused residual inspection:
  - proactive carry-through variance artifact complete
- own-scope script quality gate:
  - `ruff` clean
  - `mypy --follow-imports=silent` clean

## Final reading

- Phase `24` materially improved the broader live baseline even though the top-line
  score stayed `9 / 10`
- the important qualitative gain is that the correctness bug disappeared from the
  broader live read
- the remaining issue is narrower:
  - intermittent proactive carry-through robustness
- this phase does **not** justify reopening:
  - the Phase `22` Brainstack/native boundary
  - or the Phase `24` profile-isolation seam

## Recommended next step

- checkpoint Phase `25`
- if further polish is wanted after checkpointing, only then consider a focused
  follow-up on proactive continuity robustness
