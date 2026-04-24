# Phase 24 Context

## Why this phase exists

Phase `23` established a broader deployed-live quality baseline of `9 / 10`.

That phase did **not** reopen the Brainstack/native boundary from Phase `22`.

Instead, it surfaced two narrower but important residuals:

- a correctness / scope-hygiene bug:
  - principal-scoped durable profile bleed
- a product-quality bug:
  - proactive continuity after reset dropped a dietary carry-through

These should not be treated as one generic “memory quality” problem.

The first is more fundamental:

- if durable profile truth can bleed across principals, stronger extraction or smarter carry-through logic can amplify the wrong state

That means the next correct move is:

1. restore principal-scoped durable profile isolation
2. then harden proactive continuity carry-through on a clean scope baseline

## What is already known

### Strong signals already established

- Phase `22` boundary still reads as correct:
  - Brainstack owns durable personal memory
  - `session_search` may coexist as transcript forensics / browsing
  - `cronjob` remains native outside the owned axis
- broader deployed-live quality is mostly healthy:
  - `9 / 10`
- the two named residuals are real enough to justify a focused follow-up

### What is still unknown

- where exactly the cross-principal durable profile bleed originates:
  - ingest principal tagging
  - durable profile upsert keying
  - retrieval filtering
  - injected contract assembly
  - session-finalize / flush lifecycle
- where exactly the proactive dietary carry-through miss originates:
  - extraction
  - persistence
  - retrieval
  - packet composition
  - or answer synthesis
- whether one shared seam contributes to both bugs

## Core doctrine for this phase

This is a correctness-first phase.

It must not turn into:

- a broad SHIBA uplift phase
- a general “make Tier-2 smarter” phase
- a hidden host rewrite

The right question is:

- what is the shared seam, if any, behind these two residuals?

not:

- what extra intelligence can we add on top to mask them?

## Project guardrails with refreshed emphasis

These remain active and should be used explicitly during Phase `24`:

- donor-first
  - do not react to these residuals by inventing a new memory stack
- modularity / upstream updateability
  - prefer narrow seam repair over broad orchestration rewrites
- truth-first
  - reproduce and localize before patching
- fail-closed on the owned axis
  - if principal-scoping is broken, do not widen durable profile extraction first
- no benchmaxing
  - this is about live correctness and continuity, not benchmark movement
- no overengineering
  - do not pull SHIBA-style capability uplift into this phase unless the evidence proves it is the only credible fix path

## Product targets this phase must read against

- durable personal-memory correctness across principals
- continuity after reset without silent loss of salient constraints
- stable Brainstack/native boundary after the fix
- no new personal-memory shadow owner

## Target reading after Phase 24

If this phase goes well, the reading should be:

- durable personal-memory truth is principal-isolated again
- proactive continuity reliably carries high-salience constraints like dietary requirements
- no broader boundary rollback was required
- any remaining SHIBA-style uplift is clearly later capability work, not hidden correctness debt

## What this phase is not

- not a SHIBA-style Tier-2 uplift phase
- not a broad retrieval scoring redesign
- not a host-monolith cleanup phase
- not another broad live validation pass

## End-state invariants

1. Principal isolation invariant.
   - style/name/language/profile truth for one principal must not appear as durable truth for another principal

2. Carry-through invariant.
   - if the system keeps event/venue after reset, it should not silently drop the salient user constraint that makes the continuation useful

3. Boundary invariant.
   - Phase `22` coexistence decisions remain intact unless new direct evidence falsifies them

4. Capability-deferral invariant.
   - SHIBA-style deeper Tier-2 extraction remains a later capability option, not the default fix vehicle for this phase
