# GA Release Contract

GA READY is scoped, evidence-based, and revocable. It does not mean universal bug-free behavior in every environment.

## Feature Freeze

Allowed during GA hardening:

- P0/P1 correctness fix;
- capability preservation fix;
- approval/security fix;
- source/wizard/Docker parity fix;
- observability, failure bundle, recovery, and install/migration fix.

Blocked during GA hardening:

- new memory feature not required for P0/P1 closure;
- new donor lift;
- new provider feature;
- new prompt personality;
- broad refactor without release-blocker proof.

## READY

READY requires all:

- open P0 count is zero;
- open P1 count is zero;
- inconclusive P0/P1 count is zero;
- no manual-only proof;
- source/wizard/Docker parity is green;
- synthetic Gateway E2E is green;
- required live Discord smoke is green;
- approval/security probes are green;
- contamination and support-only leakage probes are green;
- failure-to-fix loop has zero open repairable automatic P0/P1;
- known limitations are approved, mitigated, and P2/P3 only.

## CONDITIONAL

CONDITIONAL may exist only with approved P2/P3 known limitations. It cannot contain P0/P1, inconclusive P0/P1, or manual-only proof.

## BLOCKED

BLOCKED if any:

- open P0/P1;
- inconclusive P0/P1;
- live smoke missing for supported Discord scope;
- manual-only proof;
- source/wizard/Docker mismatch;
- known limitation hides P0/P1;
- failure bundle owner cannot be classified.

## Current Phase 185 Inheritance

Phase 185 has local/source/wizard/Docker PASS and live gate BLOCKED. Therefore GA READY is blocked until live smoke passes or Discord live scope is explicitly excluded as non-GA.
