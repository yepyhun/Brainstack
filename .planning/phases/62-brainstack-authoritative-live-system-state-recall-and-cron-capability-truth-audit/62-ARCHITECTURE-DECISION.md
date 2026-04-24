# Phase 62 Architecture Decision

## decision

Phase 62 fixes current live-system authority inside Brainstack by adding a typed `live_system_state` lane that is derived directly from current Hermes runtime state.

The first provider is:
- `get_hermes_home() / "cron" / "jobs.json"`

This phase deliberately avoids a new cron lifecycle host seam.

## rationale

The validated defect was not missing transcript.

The defect was that current runtime truth was weak or absent as authoritative Brainstack state, so old transcript and continuity residue stayed easier to retrieve than current live state.

Using a Brainstack-owned runtime-state provider fixes that without:
- restoring heuristic phrase routing
- turning Phase 62 into generic Hermes cron maintenance
- requiring new callback plumbing from cron lifecycle code

## chosen shape

1. add `live_system_state` as a first-class operating-truth record type
2. synthesize typed current-state rows from the live Hermes scheduler state
3. feed those rows through the existing operating-truth interfaces:
   - `list_operating_records(...)`
   - `search_operating_records(...)`
   - `get_operating_context_snapshot(...)`
4. render those rows in the `Operating Context` system prompt section
5. state explicitly that only listed live runtime state is authoritative for currently active autonomous mechanisms

## rejected alternatives

### transcript demotion alone

Rejected because it suppresses bad evidence without providing explicit current-state authority.

### new cron host seam first

Rejected because the current authority defect can be corrected inside Brainstack by reading the existing scheduler state file directly.

### phrase routing for heartbeat/evolver/pulse

Rejected because it violates the no-heuristic rule and overfits to the current thread.

## authority model

- current live-system truth is now carried by typed Brainstack state
- transcript and continuity remain historical/supporting evidence only
- absence is representable:
  - when no current scheduler jobs exist, Brainstack emits an explicit absence row
- when some live runtime state exists, anything not listed is no longer allowed to silently inherit authority from historical transcript alone

## boundary verdict

The cron file-write incident remains a boundary finding, not a Brainstack implementation target.

Current evidence-backed verdict:
- false capability claim without tool attempt

## host seam verdict

No new host seam was required for the Phase 62 Brainstack correction.
