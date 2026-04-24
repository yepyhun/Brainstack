# Phase 62 Implementation Contract

## execution intent

Phase 62 must make Brainstack authoritative about live autonomous mechanisms.

If the user asks whether heartbeat, pulse, evolver, or similar long-lived systems are active, the answer must come from Brainstack-owned current-state truth first, not from transcript residue.

## architecture discipline

### 1. use existing operating-truth structures first

Preferred structures:
- `operating_records`
- `operating_context`
- explicit record types for current live mechanisms if existing types are insufficient

Disfavored structures:
- transcript hacks
- profile abuse as a runtime-state lane
- a second ad hoc "daemon state" memory table unless existing operating truth is proven insufficient

### 2. separate "current system state" from "recent recap"

Phase 61 fixed restart recap.

Phase 62 must not blur that into a generic "everything recent" route.

This phase is about:
- whether a mechanism is currently live
- whether it is currently absent
- whether it was only previously discussed or previously deployed

That is a distinct authority problem from broad recent-work recap.

### 3. current-state truth must outrank transcript residue

For live-system questions:
- authoritative operating truth must be checked first
- transcript and continuity may support explanation
- transcript and continuity must not silently act as current truth when operating truth is absent or stale

### 4. absence must be representable

It is not enough to store "heartbeat was set up once".

The memory design must support:
- live
- absent
- stale / superseded / historical

without forcing the model to guess from old prose.

### 5. cron capability-truth investigation is a bounded side workstream

Allowed work:
- inspect cron tool surface
- inspect cron session artifacts
- determine whether the assistant falsely claimed incapability

Rejected work:
- broad cron engine rewrites
- generic file-permission debugging not needed for the authority verdict
- any host surgery that does not support the Brainstack-owned truth model

### 6. no heuristic route farm

This phase must not reintroduce:
- keyword lists for `heartbeat`
- phrase tables for `is it running`
- locale-specific route rules
- exact-sentence rescue logic

If a new route/classification is needed, it must come through the same structured, bounded, non-phrase-farm approach used after Phase 61.

### 7. source-of-truth rule

Any Brainstack fix must land first in:
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`

Any live proof must then be reproduced on:
- `/home/lauratom/Asztal/ai/veglegeshermes-source`

### 8. closeout truth rule

The closeout must explicitly separate:
- the Brainstack authoritative-state defect
- the cron capability-truth boundary verdict

It must not collapse them into one fuzzy "memory/kernel/runtime was broken" summary.
