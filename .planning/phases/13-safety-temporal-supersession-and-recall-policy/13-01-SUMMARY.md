# Phase 13 Summary

## What Changed
- Added Brainstack-owned temporal helpers:
  - `brainstack/temporal.py`
- Added Brainstack-owned provenance helpers:
  - `brainstack/provenance.py`
- Hardened the durable write path so profile, continuity, relation, and graph-state records normalize and merge temporal/provenance metadata at the store boundary:
  - `brainstack/db.py`
- Extended the reconciler so Tier-2 candidates carry deterministic metadata into profile/state/relation writes:
  - `brainstack/reconciler.py`
- Updated recall formatting and control-plane policy so:
  - current truth is preferred by default
  - prior truth appears only when temporal/conflict/explanatory context makes it useful
  - conflicts surface explicitly
  - provenance expands only on important or uncertain cases
  - recall output stays bounded
  - `brainstack/retrieval.py`
  - `brainstack/control_plane.py`

## Core Phase-13 Decisions
- Kept the single Brainstack provider runtime:
  - no second service
  - no donor-owned subsystem
  - no new memory layer
- Centralized temporal/provenance normalization in the store layer so mixed direct callers cannot drift into half-wired metadata behavior.
- Kept usefulness scoring out of scope:
  - adaptive telemetry remains a later phase
- Kept corpus scoring out of scope:
  - Phase 13 only closes temporal/provenance/recall safety for the existing shelves

## Anti-Half-Wire Proof
- The live Bestie container now imports:
  - `plugins.memory.brainstack.temporal`
  - `plugins.memory.brainstack.provenance`
- The live retrieval module contains the new recall-safety controls:
  - `show_graph_history`
  - `summarize_provenance`
- Runtime proof passed for all target behaviors:
  - compact query shows only current truth
  - temporal query shows prior truth when needed
  - conflict query surfaces the conflict
  - conflict query shows bounded basis/provenance

## Local Verification
- Targeted Phase-13 tests passed:
  - `18 passed in 3.10s`
- Covered cases include:
  - temporal normalization
  - point-in-time effectiveness
  - provenance merge and bounded rendering
  - supersession behavior
  - conflict recall behavior
  - non-temporal current-truth preference

## Installed Runtime Verification
- Bestie Docker rebuild completed successfully.
- Live container status:
  - `healthy`
- Live runtime proof output:
  - `compact_has_current=true`
  - `compact_hides_prior=true`
  - `temporal_has_prior=true`
  - `conflict_surfaces=true`
  - `conflict_shows_basis=true`

## Outcome
Phase 13 turned Phase-12 extraction into a safer memory system:
- corrected truth now preserves old state instead of flattening it
- important recall can explain its basis without provenance spam
- the default recall path remains token-disciplined and current-truth-first
