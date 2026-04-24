# Phase 6 Plan

## Goal
Complete native displacement with the smallest viable host patch set.

## Workstreams

### W1. Disable Paths
Define and implement the off path for built-in memory and built-in profile behavior.

### W2. Compatibility Patch
Define the smallest host modifications required for live-path displacement.

### W3. Safety Checks
Define how we prove the old path is no longer active.

## Exit Gate
Hermes no longer depends on the built-in live memory behavior for the Brainstack flow.

## After Phase Review

Recommended next step if the gate truly passes:
- execute Phase 7

Recommended agent effort:
- high

Re-evaluation rule:
- if native memory still leaks through the live path, stay in this phase
