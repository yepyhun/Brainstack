# Phase 61 Implementation Contract

## execution intent

Phase 61 must fix the Brainstack recent-work recap contract at the memory-kernel level.

The implementation target is:
- recent work survives restart in compact durable form
- broad recap queries retrieve that form through Brainstack
- transcript search becomes secondary, not primary

## required architecture discipline

### 1. prefer existing Brainstack structures first

Preferred structures:
- `operating_records`
- `operating_context`
- compact continuity support

Disfavored structures:
- new ad hoc side tables
- raw transcript mirrors
- host-owned recap ledgers

If a new Brainstack-owned structure becomes necessary, the execution must first explain why existing `operating_truth` cannot carry the contract cleanly.

### 2. recent-work recap is its own recall class

The implementation may add a bounded recap-recall route for questions about:
- what we were doing
- what was fixed
- whether a recent phase landed
- what happened before restart

But it must not become:
- a giant general-purpose fuzzy search mode
- a locale-specific phrase table
- an exact-thread rescue path

It also must not be implemented by widening the `task_like` route until task lookup and recap lookup become one mixed lane.

### 3. durable recent-work truth must be compact

Allowed durable shapes:
- concise active-work summaries
- concise completed-outcome summaries
- concise explicit discard/abandon records when they materially affect recap truth

Rejected durable shapes:
- raw turn-by-turn logs
- large prose dumps
- every intermediate implementation step
- "assistant says it fixed X" without the stronger grounding already required by Phase 60

### 3.1 scope model is already constrained

`operating_records` should be treated as:
- principal-scoped truth
- with session provenance

The implementation must reuse that model unless it can prove a concrete insufficiency.

Do not reopen scope design as if Brainstack had no existing answer here.

### 4. transcript fallback stays bounded

If transcript evidence is still needed:
- it must be bounded
- it must come after operating truth
- it must not dominate the ordinary packet
- it must not be used to hide an empty recent-work operating lane

### 5. host seam rule

Host changes are allowed only if Brainstack cannot otherwise form restart-surviving recent-work truth from the current hooks.

Any such seam must be:
- narrow
- explicit
- Brainstack-correctness-motivated
- upstream-survivable

Rejected seam shapes:
- generic `/resume` redesign
- generic session_search rewrite as the main answer
- generic gateway UX cleanup

### 6. promotion timing rule

The implementation must explicitly decide how recent-work truth is promoted.

Accepted default direction:
- bounded ongoing promotion for active/recent work
- plus session-end consolidation for compact recap summaries

Rejected default direction:
- session-end-only promotion presented as sufficient without proof

## required design decisions to freeze before execution

The execution must freeze and then honor explicit answers to these:

1. **Recent-work durable lane**
   - use existing `operating_records` only
   - or justify a narrowly extended Brainstack-owned lane

2. **Recap-route detection**
   - define the bounded semantics for "recent-work recap" queries
   - show why the chosen detector is not a phrase farm
   - show how it remains distinct from `task_like`

3. **Projection order**
   - specify the exact evidence order for recap queries

4. **Discard semantics**
   - specify how abandoned/superseded work is preserved so recap answers do not hallucinate it as still active

5. **Promotion timing**
   - specify when recent-work operating truth is written
   - justify why that timing survives restart/interrupt paths

## accepted change shapes

- Brainstack operating-truth capture hardening for recent work
- Brainstack recap-route query analysis
- Brainstack recap-focused query expansion or route shaping
- Brainstack packet rendering changes for compact recent-work projection
- narrow provenance reuse from Phase 60 where needed to prevent polluted recap summaries
- minimal installer/wizard updates only if the same Brainstack behavior must reproduce on fresh installs
- bounded active-work promotion and session-end consolidation logic for recent-work operating truth

## rejected change shapes

- tuning `session_search` and calling it the fix
- exact matching for `phase 60`
- special casing one user id, one Discord thread, or one session id
- summary blobs that materially worsen token usage
- generic host cleanup without a Brainstack contract reason
- implementing recap by piggybacking on `task_like`
- session-end-only promotion if restart survival remains unproven

## proof obligations for the later execute step

The execute step must prove all of the following:

1. **Non-empty recap packet**
   - a broad recap query after restart yields non-empty Brainstack recall

2. **Operating truth present**
   - recent work is represented in a durable operating lane, not only transcript/continuity residue
   - the result explains whether the lane was updated during active work, at session end, or both

3. **Cross-session recall works**
   - recap does not silently fail because the relevant work was stored in a previous session id
   - the result uses the existing principal-scoped truth model with session provenance rather than a one-off scope trick

4. **Transcript search is demoted**
   - the same recap query does not need `session_search` when Brainstack already has enough durable signal

5. **Boundedness preserved**
   - the fix does not bloat the ordinary packet into a transcript dump

## inspector note

This phase will be judged harshly if it "works" only because:
- one phrase was hardcoded
- one thread was rescued
- one timeout was shortened
- or the transcript-search path got faster while the Brainstack recall packet stayed empty

The phase only counts as correct if the memory kernel itself becomes capable of restart recap.
