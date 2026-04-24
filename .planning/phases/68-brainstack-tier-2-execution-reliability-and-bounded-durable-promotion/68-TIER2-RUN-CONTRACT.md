# Phase 68 Tier-2 Run Contract

## Contract

Every Tier-2 run result is represented as a bounded run record:

- `run_id`
- session and turn
- trigger reason
- request status
- parse status
- transcript count
- extracted counts
- action counts
- durable write count
- no-op reasons
- error reason
- duration

The provider may keep an in-memory recent history, but the durable Brainstack DB is the source for cross-session observability.

## Provenance Gate

Assistant-authored candidates are rejected before durable promotion. This applies to profile, style contract, graph state/relation, typed entity, temporal event, and decision candidates when the candidate metadata/provenance marks assistant authorship.

## No-Op Semantics

No-op reasons distinguish:

- no store
- no eligible transcript turns
- extractor returned an empty payload
- no durable writes were performed
- all candidates were rejected or were no-ops

## Boundary

Tier-2 may promote bounded memory records through Brainstack-owned write paths. It does not execute tasks, enforce runtime approval, or become a behavior governor.
