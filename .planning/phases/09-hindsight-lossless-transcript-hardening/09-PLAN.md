# Phase 9 Plan

## Goal
Capture the everyday continuity upside of lossless transcript retention without importing a second runtime lifecycle into Hermes.

## Workstreams

### W1. Transcript Shelf
Add a provider-internal raw turn store and bounded session snapshots behind Brainstack seams.

### W2. Retrieval Discipline
Surface transcript evidence only when the query genuinely needs prior wording, decisions, or conversational history.

### W3. Update Safety
Keep `hermes-lcm` as a donor pattern only; do not create a parallel context engine or new model-facing tools in this phase.

## Exit Gate
Brainstack gains transcript continuity hardening while ownership, prompt discipline, and host compatibility remain clean.

## After Phase Review

Recommended next step if the gate truly passes:
- run milestone-level verification and integration review

Recommended agent effort:
- high

Re-evaluation rule:
- if the implementation starts looking like a second engine instead of an internal shelf, cut scope back before phase closure
