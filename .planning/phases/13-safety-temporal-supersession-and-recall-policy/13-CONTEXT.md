# Phase 13 Context

## Goal
Harden Brainstack's post-Phase-12 write and recall path so temporal change, provenance basis, and recall safety become explicit and reliable without adding a second runtime, a new memory layer, or noisy provenance spam.

## Why This Phase Exists
Phase `12` proved that Brainstack can now extract durable profile/state/relation material through a non-blocking Tier-2 path and write it into the existing shelves. That is necessary, but not yet sufficient.

Without Phase `13`, the system still has three practical weaknesses:
- corrected state can be written, but the temporal contract is still implicit and uneven across write/read paths
- provenance exists only as scattered metadata, so important or low-confidence recall cannot explain its basis cleanly
- recall policy does not yet explicitly prefer current truth, bounded historical truth, and conflict-safe surfacing under token discipline

Phase `13` exists to make the Phase `12` intelligence trustworthy rather than merely impressive.

## Architecture Decision

### Chosen Direction
- keep the existing 3-layer Brainstack storage model intact
- do **not** add a new runtime, service, or donor-owned subsystem
- add Brainstack-owned helper modules for:
  - temporal normalization / point-in-time effectiveness
  - provenance normalization / merge
  - bounded recall-safety policy
- apply those helpers to existing:
  - store writes
  - reconciler decisions
  - retrieval rendering

### Donor Use Rule
- `kernel_memory_temporal.py` is a targeted donor for helper shape, not a subsystem transplant
- `kernel_memory_provenance.py` is the preferred donor for normalization / merge shape, but must be reshaped to Brainstack field names
- `kernel_memory_feedback_priority.py` is **not** Phase `13` scope; adaptive usefulness scoring stays in Phase `15`

## Phase Boundary

### In Scope
- Brainstack-owned `temporal.py` helper module
- Brainstack-owned `provenance.py` helper module
- write-path normalization for temporal/provenance fields in the existing Tier-1/Tier-2 reconciler/store flow
- recall policy changes so:
  - current truth wins by default
  - prior truth appears only when useful and bounded
  - conflict state is surfaced explicitly
  - provenance appears when confidence is low or the case is important
- bounded tests for:
  - supersession
  - point-in-time effectiveness
  - provenance merge
  - recall rendering behavior
  - token-discipline no-regression

### Explicitly Out Of Scope
- adaptive usefulness / Bayesian scoring
- corpus intelligence expansion
- multilingual extraction changes
- broad everyday proving of user-visible quality
- graph-backed late-stage anti-half-wire audit

## Temporal Requirements
- superseded state must remain historically visible instead of being destructively overwritten
- recall must be able to distinguish:
  - current truth
  - prior truth
  - conflicting truth
- temporal helpers must stay deterministic and cheap
- point-in-time effectiveness checks must work on current Brainstack records instead of requiring a second temporal store

## Provenance Requirements
- provenance fields must be normalized before durable write and before recall rendering
- multiple evidence sources must be mergeable without duplicate list growth
- provenance must remain bounded and quiet by default
- important or uncertain recall must be able to expose its basis cleanly

## Recall Safety Requirements
- current truth should be preferred over stale truth by default
- stale truth should only appear when it adds value, for example correction history or explicit comparison
- open conflicts must never be silently flattened into one winner
- recall formatting must preserve token discipline and avoid provenance spam

## Anti-Half-Wire Requirements
- temporal/provenance helpers must be used by the real reconciler and retrieval path, not only by tests
- no parallel \"old metadata path\" may remain as the actual owner after the new helpers are introduced
- schema additions must stay inside the single Brainstack provider architecture and install/update workflow

## Canonical References
- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/13-safety-temporal-supersession-and-recall-policy/13-DONOR-NOTES.md`
- `/home/lauratom/Asztal/ai/hermes-agent-port/agent/kernel_memory_temporal.py`
- `/home/lauratom/Asztal/ai/hermes-agent-port/agent/kernel_memory_provenance.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/db.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/reconciler.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/retrieval.py`

## Output Expectation
Phase `13` should end with Brainstack-owned temporal and provenance helpers, explicit recall-safety behavior on top of the live Tier-2 path, and bounded proof that current/prior/conflict/provenance cases now behave predictably without regressing token discipline.
