# Phase 64 Implementation Contract

## execution intent

Design a runtime-side intake and execution contract that consumes Brainstack-authored state and produces bounded proactive behavior without collapsing ownership boundaries.

## required architecture discipline

### 1. Brainstack remains state authority

The runtime may consume Brainstack outputs, but it must not replace them with ad hoc transcript reconstruction or duplicate shadow state.

### 2. intake must be explicit

If the runtime consumes inbox tasks, they must arrive as explicit typed envelopes. No “maybe this sentence sounds like a task” intake path is acceptable here.

### 3. approval must be metadata-driven

Unknown-domain or blocked-domain handling must be based on explicit task metadata and durable policy state, not keyword heuristics over arbitrary text.

### 4. session-start recovery must be bounded

The startup sequence must be deterministic, bounded, and cheap enough to run reliably at every session start.

The target operating model is bounded startup initiative, not hidden background cognition.

### 5. writeback must be typed

Execution results should become typed status or artifact updates that later sessions can reuse without re-reading transcripts.

The runtime must not write directly into Brainstack persistence as an ownership shortcut. Writeback must cross an explicit Brainstack-owned seam/provider/API.

### 6. no fake autonomy

The system may wake, inspect, and act within bounded rules, but it must not claim continuous autonomous agency it does not actually possess.

### 7. generality rule

The contract must describe a reusable runtime pattern, not a Bestie-only pile of local script conventions.

### 8. host seam rule

If runtime hooks are needed, keep them explicit and minimal. Do not spread logic across multiple hidden host seams when one stable intake seam would do.

### 9. closeout truth rule

The final design must clearly state what the runtime can now do, what Brainstack can now supply, and what still remains outside this phase.

## required design decisions to freeze before execution

- exact inbox task schema
- exact intake order at session start
- exact approval-state model
- exact writeback format and owner
- exact boundary between cron wake behavior and session-start behavior
- exact proof budget for cheap startup behavior

## accepted change shapes

- design of JSON task envelopes
- runtime intake orchestration
- approval-gate integration design
- typed writeback design
- explicit boundary docs between Brainstack and Hermes runtime

## rejected change shapes

- heuristic text-domain classifiers
- transcript-driven pseudo-recovery
- cron scripts as primary state authority
- hidden runtime state outside the agreed contract
- vague “we will just check everything on startup” designs without bounded order and owner

## proof obligations for the later execute step

- prove a session can start, inspect pending typed work, and act or block deterministically
- prove blocked-domain items do not auto-run
- prove completed or stale tasks do not keep resurfacing as fresh work
- prove the same contract works beyond this one concrete profile

## inspector note

This phase is where “entity-like” behavior becomes a real runtime pattern instead of a narrative claim. The inspection risk is not raw code complexity; it is ownership blur and fake autonomy. Keep the boundary sharp.
