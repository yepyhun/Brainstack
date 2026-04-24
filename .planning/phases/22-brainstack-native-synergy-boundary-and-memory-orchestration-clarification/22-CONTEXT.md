# Phase 22 Context

## Why this phase exists

Phase 21 repaired the personal-memory / communication-contract axis correctly.

It also surfaced a broader architectural question that should not be answered reactively:

- where should Brainstack be the authoritative owner?
- where should native Hermes capabilities remain in place?
- where is the current boundary over-displacing native behavior instead of creating the right layered synergy?

The goal of this phase is not "make Brainstack replace more things".

The goal is the opposite:

- keep Brainstack as the owner only where that ownership is product-defining
- preserve native host capabilities where they remain structurally better or cheaper to maintain
- clarify the boundary so future work does not silently create duplicate ownership or unnecessary maintenance burden

## What the post-Phase-21 audit established

### Stronger than expected

- the cron / automation boundary now looks correct
  - native cron survives
  - only personal-memory shadow-owner usage is blocked
- gateway finalize already shows a good integration pattern
  - native lifecycle shell
  - Brainstack-owned provider finalize
- `SOUL.md` currently behaves as bounded compatibility shell, not as the owner of personal-memory truth

### Potentially over-displaced

- `session_search` appears to belong to a different capability class:
  - transcript forensics
  - explicit session browsing
  - search/summarize of prior raw conversation sessions
- that is not the same as durable personal-memory ownership
- hiding it wholesale in Brainstack-only mode may therefore be over-displacement rather than clean ownership

### Architectural clarity gap

- legacy built-in memory still lives directly in `run_agent.py`
- plugin memory lives behind `MemoryManager`
- current docs imply a cleaner builtin+external layering than the runtime actually implements
- this is not a direct Phase 21 blocker, but it is a real architectural clarity and maintenance problem

## Core doctrine for this phase

This phase must decide boundaries by capability class, not by ideology.

The right question is not:

- "can Brainstack replace it?"

The right questions are:

1. what product capability is this feature actually serving?
2. is it on the same ownership axis as Brainstack's durable personal memory?
3. does coexistence create clean layering or conflicting truth?
4. if Brainstack and native Hermes both participate, can the boundary stay explicit and cheap to maintain?

## Project guardrails with refreshed emphasis

These are not background values only. They must actively govern Phase 22 decisions:

- donor-first
  - do not replace upstream/native behavior unless the boundary truth proves we should
- modularity / upstream updateability
  - prefer thin integration and clear ownership over custom replacement work
- truth-first
  - runtime truth outranks elegant theory
- fail-closed on the owned axis
  - personal-memory shadow owners must stay closed
- no benchmaxing
  - this phase is about product architecture, not benchmark shape
- no overengineering
  - robustness is good
  - unnecessary framework growth is failure

## Target architecture after Phase 22

After this phase, the system should have a cleaner capability-partition doctrine:

- Brainstack owns:
  - durable personal identity
  - durable user preferences
  - communication contract
  - long-range relation-tracking and graph/corpus-backed recall
- native Hermes may continue to own:
  - explicit session forensics / transcript browsing
  - scheduling / automation
  - general tool ecosystem behaviors outside the personal-memory axis
- orchestration should make this visible:
  - one explicit owner per truth axis
  - coexistence where capability classes differ
  - no accidental duplicate owners

## End-state invariants

1. Ownership-axis invariant.
   - Brainstack remains the owner of durable personal-memory truth.

2. Coexistence invariant.
   - native capabilities that do not compete on that truth axis remain available if they add real value.

3. No-shadow-owner invariant.
   - coexistence must not create a second hidden persistence or retrieval owner for the same personal-memory truth.

4. Orchestration-clarity invariant.
   - runtime architecture and documentation must describe the same layering model.

5. Maintenance invariant.
   - the chosen boundary must reduce long-term custom maintenance, not increase it.

## What this phase is not

- not a Phase 21 reopen
- not a benchmark phase
- not a broad host-monolith cleanup
- not a "replace all native memory with Brainstack" campaign
- not a docs-only cleanup without runtime truth

## Honest target

The honest best result is not necessarily "more Brainstack".

The honest best result is:

- one clearer ownership boundary
- one or more restored coexistence points if they are architecturally justified
- and one cleaner orchestration story between legacy built-in memory and plugin memory
