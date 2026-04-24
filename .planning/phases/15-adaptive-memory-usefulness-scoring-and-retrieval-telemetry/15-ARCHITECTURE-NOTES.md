# Phase 15 Architecture Notes

Captured: 2026-04-11
Status: pre-planning note

## Why This Exists
Static confidence alone is not enough for long-lived Brainstack recall.

If an item keeps being recalled but almost never helps, the system should eventually learn that it is low-value.
If an item repeatedly proves useful, the system should become more willing to keep it in bounded recall.

## Placement Decision
- not part of Phase 10.2
- not part of Phase 11
- not part of Phase 12
- not part of Phase 13 core safety/provenance work
- best placed after Phase 14 proving, as a later optimization layer

Reason:
- first we need clean ingest
- then explicit extraction pipeline
- then multilingual extraction + reconciliation
- then temporal/provenance safety
- then real-world proof
- only after that does adaptive usefulness scoring become trustworthy

## Donor Inspiration
Source:
- `/home/lauratom/Asztal/ai/hermes-agent-port/agent/kernel_memory_feedback_priority.py`

Useful donor ideas:
- usefulness telemetry
- low-value retrieval detection
- retrieval miss tracking
- confidence-floor / verification-tier style shaping

## Important Architectural Verdict
Do not carry over the donor's simplified ratio logic as the final Brainstack design.

Why:
- Brainstack has multiple shelves, not one flat memory surface
- provenance matters
- temporal state matters
- graph/profile/corpus/continuity should not be ranked by one naive counter alone

## Preferred Brainstack Direction
When this phase is planned, prefer a Brainstack-shaped model such as:
- usefulness counters or alpha/beta-style evidence
- shelf-aware signals
- provenance / verification-tier weighting
- bounded recall telemetry
- low-value suppression without destructive deletion

## Optional Early Hook
If Phase 13 can cheaply add schema fields or metadata hooks for later telemetry collection, that is acceptable.
But the actual adaptive prioritization should remain a later activation, not an accidental early rollout.
