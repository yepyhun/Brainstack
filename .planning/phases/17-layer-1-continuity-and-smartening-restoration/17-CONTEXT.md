# Phase 17 Context

## Discuss Outcome

The Phase `17` direction is now explicitly locked.

This phase is **not** allowed to:

- tune the current Tier-1 heuristics
- add a temporary heuristic bridge
- keep the old heuristic path as the real center while donor logic sits beside it

Phase `17` must replace the current L1 center with a donor-first primary path.

## What “Donor-First L1” Means

For Phase `17`, the primary L1 behavior must be:

- hybrid retrieval as the main path, not a fallback
- at minimum:
  - vector similarity
  - FTS / keyword search
  - temporal signal
- if useful, entity/link signals may assist

This is aligned with the donor direction:

- Hindsight: semantic + keyword + graph + temporal
- Graphiti: semantic + BM25/FTS + graph traversal

The project must **not** treat hybrid retrieval as a backup under the old path.
It must become the actual path.

The accepted architecture now also clarifies that:

- L1 is the executive retrieval/smartening layer
- it is not another long-term storage engine
- it should combine results from the donor-backed graph and corpus layers rather than pretending Brainstack-local glue is enough

For planning purposes, the target shape is:

- Hindsight/TEMPR-style fusion logic
- over:
  - Graphiti-shaped L2 retrieval signals
  - MemPalace-shaped L3 retrieval signals

## Hard Rule: Zero Handwritten Language Heuristics

For this recovery track, “zero heuristics” means:

- no handwritten language-specific trigger lists
- no regex-driven preference or identity extraction growth
- no “if this word appears, save this memory” logic as the main intelligence path

This is a multilingual safety rule.

These are still allowed because they are engine-level retrieval methods, not the bad kind of heuristic:

- vector similarity
- FTS / BM25
- temporal weighting
- graph distance
- RRF or similar fusion

## Brainstack Job vs Donor Job

This is now clarified in plain language.

### Brainstack job

- keep the system together
- own shell state and host boundaries
- own cross-store ingest consistency
- preserve privacy / ownership rules
- preserve safety
- package recall for the model
- remain installer-carried and update-safe

### Donor job

- provide the actual memory intelligence
- decide what past information matters
- retrieve relevant context well
- make the agent feel smarter across sessions

For end-state architecture:

- truth / time / provenance should be primarily Graphiti-shaped, not permanently Brainstack-local intelligence
- Phase `17` is about L1 smartening
- Phase `18` will continue the move of truth/time/provenance strength back toward the Graphiti side
- SQLite is no longer the target engine for all memory intelligence
- embedded donor-aligned backends are now the accepted recovery target:
  - Kuzu for L2
  - Chroma for L3

## High Acceptance Bar

Phase `17` is not allowed to pass on a soft “better than before” basis.

The bar is:

- donor-level or better on the donor’s own domain
- no fallback-centered architecture
- no heuristic-centered architecture
- visible “agent smartening”, not only better storage

If the result still feels like:

- transcript + local glue + nicer packaging

then Phase `17` fails.

## Eval Ladder

The benchmark is not the purpose.
Real smartening is the purpose.

But the phase still needs a faster test ladder than repeated slow LongMemEval runs.

### Gate A: Fast acceptance suite

Adapt the existing kernel-memory acceptance scenarios to Brainstack.

Purpose:

- fast deterministic gate
- repeated during implementation

### Gate B: Mini smartening suite

Add a small Brainstack-specific suite focused on:

- whether the agent notices what matters
- whether it carries forward the right thing
- whether follow-up behavior is smarter

This suite must validate actual donor-restored smartening, not only nicer local packaging.

### Gate C: Mini LongMemEval subset

Keep a small benchmark subset as a regression guard.

### Gate D: Final boss

Run the full or large LongMemEval only at the end of the restoration gate, not as the main iteration loop.

## Non-Negotiable Rule

The benchmark may confirm success.
It may not define success by itself.

The core goal of Phase `17` is:

- the agent learns
- the agent carries forward important context better
- the agent feels meaningfully smarter

## Ingest Note For Later Phases

Large-corpus recovery will require many L2 extraction calls during ingest.

That means later phases must assume:

- batching
- rate limiting
- resumable offline ingest
- retry after partial failure

This is not a new subsystem by itself.
It is part of the Brainstack shell's cross-store consistency responsibility.

## Recommended Effort

- `xhigh`
