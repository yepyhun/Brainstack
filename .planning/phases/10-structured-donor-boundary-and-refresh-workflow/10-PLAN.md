# Phase 10 Plan

## Goal
Refactor the current donor-inspired Brainstack stack into a structured donor-boundary model that is much more modular and refreshable without overselling it as full automatic donor updating.

## Workstreams

### W1. Donor Boundary Contract
Define explicit donor ownership, local adapter seams, and donor registry/manifest artifacts for the in-scope donor-backed layers.

### W2. Physical Separation
Move donor-facing logic and metadata into obvious, isolated modules so Brainstack-owned orchestration code is no longer mixed with donor-shaped substrate code.

### W3. Refresh Workflow
Add a bounded refresh workflow that records donor version/commit baselines, checks upstream drift, and runs compatibility smoke tests without pretending to auto-merge everything.

### W4. Anti-Half-Wire Proof
Add invariants and negative tests that prove the refactor did not leave silent fallback paths, dead seams, or fake adapter layers behind.

## Exit Gate
Brainstack becomes materially more modular and update-friendly, donor boundaries become explicit, and refresh work becomes auditable instead of ad-hoc, while the single-owner runtime contract stays intact.

## After Phase Review

Recommended next step if the gate truly passes:
- either milestone-level completion review
- or a later dedicated full donor-update automation phase if one-click updating still remains a priority

Recommended agent effort:
- high

Re-evaluation rule:
- if the implementation starts claiming full automatic donor updating without real compatibility guarantees, cut scope back and keep the phase honest
