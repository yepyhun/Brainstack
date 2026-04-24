## Outcome

- `27` closed as a **selective donor-uptake** phase, not `hermes-lcm` integration.
- Two candidate slices passed the portability, overlap, and utility gates:
  - `source-window / compaction provenance`
  - `explicit lifecycle / frontier state`
- Two candidate slices were explicitly deferred:
  - `bounded expand/search ergonomics`
  - `ignored/stateless-session filtering`

## What Changed

### Brainstack source

- `brainstack/donors/continuity_adapter.py`
  - extended the existing snapshot write seam instead of creating a second compaction structure
  - bounded snapshot provenance is now stored under `metadata.provenance`
  - captured fields include:
    - `input_message_count`
    - `captured_message_count`
    - `source_window_start`
    - `window_digest`
    - bounded `source_window` previews
- `brainstack/db.py`
  - added a thin `continuity_lifecycle_state` substrate
  - new state captures:
    - current frontier turn
    - last snapshot kind / turn / counts / digest / timestamp
    - last finalized turn / timestamp
  - no second runtime, no new host plugin slot, no second truth owner
- `brainstack/__init__.py`
  - wired the new lifecycle state only at the two real host seams:
    - `on_pre_compress`
    - `on_session_end`

### Tests

- new focused lifecycle test file:
  - `tests/test_brainstack_lifecycle_state.py`
- extended existing donor-boundary coverage without turning those tests into provenance-detail tests

## Portability / Overlap Verdict

### 1. Source-window / compaction provenance

- preflight truth:
  - partial overlap already existed via continuity snapshots and provenance metadata support
- decision:
  - extend the existing snapshot seam
- result:
  - landed

### 2. Lifecycle / frontier state

- preflight truth:
  - no clean existing analogue was present
- decision:
  - add the smallest viable Brainstack-owned host-state substrate
- result:
  - landed

### 3. Bounded expand/search ergonomics

- preflight truth:
  - partial overlap already exists through retrieval shaping and bounded snippet packing
  - the donor ergonomics depend more heavily on donor runtime assumptions than the first two slices
- decision:
  - defer
- reason:
  - not enough clean ROI yet without risking token or host-surface creep

### 4. Ignored/stateless-session filtering

- preflight truth:
  - no strong noisy-session evidence was established
- decision:
  - defer
- reason:
  - conditional candidate failed the evidence gate

## Validation

- targeted Brainstack slice:
  - `pytest tests/test_brainstack_donor_boundaries.py tests/test_brainstack_lifecycle_state.py tests/test_brainstack_transcript_shelf.py -q`
  - result: `14 passed`
- broader affected Brainstack slice:
  - `PYTHONPATH=. pytest tests/test_brainstack_replacement_contract.py tests/test_brainstack_donor_boundaries.py tests/test_brainstack_lifecycle_state.py tests/test_brainstack_transcript_shelf.py -q`
  - result: `17 passed`
- quality gates:
  - `ruff check brainstack/__init__.py brainstack/db.py brainstack/donors/continuity_adapter.py tests/test_brainstack_donor_boundaries.py tests/test_brainstack_lifecycle_state.py`
  - `mypy --follow-imports=silent --ignore-missing-imports brainstack/__init__.py brainstack/db.py brainstack/donors/continuity_adapter.py`
  - result: clean

## Final Reading

- This phase improved the host-side seam around Brainstack without turning Brainstack into a second host runtime.
- The landed changes are bounded, donor-first, and low-token:
  - provenance is richer for audit/expansion, but it does not force larger prompt blocks
  - lifecycle state is explicit, but it does not add a new runtime owner or session framework
- Bestie was intentionally left untouched in this phase.
  - later validation / mirroring can happen from Brainstack source truth if needed

## Recommended Next Step

- checkpoint Phase `27`
