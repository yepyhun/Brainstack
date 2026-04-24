# Phase 13 Donor Notes

Captured: 2026-04-11
Status: pre-planning note

## Preferred Donor Candidates

### 1. Temporal normalization donor
Source:
- `/home/lauratom/Asztal/ai/hermes-agent-port/agent/kernel_memory_temporal.py`

Why it is promising:
- very small and reviewable
- language-neutral
- directly matches the future Phase 13 need for temporal visibility and supersession-safe recall

What looks reusable:
- `normalize_temporal_fields(...)`
- `record_is_effective_at(record, as_of=...)`

Recommended use in Brainstack:
- do not port it as a whole subsystem
- adopt it as a small helper layer around Brainstack temporal records / recall policy
- use it to normalize:
  - `observed_at`
  - `valid_at`
  - `valid_from`
  - `valid_to`
  - `supersedes`
  - `superseded_by`
- use point-in-time effectiveness checks when later recall must decide whether a prior or current state should be shown

Important note:
- this is a helper donor for Phase 13 safety/policy work
- it is not a replacement for Brainstack graph/state storage

### 2. Provenance normalization and merge donor
Source:
- `/home/lauratom/Asztal/ai/hermes-agent-port/agent/kernel_memory_provenance.py`

Why it is promising:
- deterministic
- cheap
- language-neutral
- matches the future need for provenance-aware recall and multi-source reconciliation

What looks reusable:
- `normalize_provenance(...)`
- `merge_provenance(...)`

Recommended use in Brainstack:
- use it as the preferred donor shape for provenance normalization before durable write / recall formatting
- use it to merge multiple evidence sources from:
  - transcript
  - continuity
  - graph
  - future Tier-2 extraction outputs
- keep list-like provenance fields normalized and deduplicated

Important note:
- this should support the later recall-policy work in Phase 13
- especially when the system needs to expose “what is this based on?” without noisy per-turn spam

## Current Verdict
- both files are good donor candidates for Phase 13
- `kernel_memory_temporal.py` = good targeted donor
- `kernel_memory_provenance.py` = very strong donor

## Architectural Decision Reminder
- do not adopt these in Phase 10.2
- do not treat them as reasons to skip Phase 11 or Phase 12
- revisit them explicitly during Phase 13 planning
- preferred adoption mode is selective donor reuse, not blind full-port
