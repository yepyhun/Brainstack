# Phase 16 Context

## Why This Phase Exists

Brainstack Layer 2 is now structurally correct, but still not strong enough for the intended product.

Today it is good at:

- explicit entities
- explicit relations
- explicit current state
- temporal supersession
- conflict surfacing
- provenance-aware recall

But it is still too weak in the places that make a graph feel genuinely intelligent:

- unstated but real links are often missed
- graph retrieval is still too lexical and row-oriented
- recall packaging does not cleanly separate:
  - current explicit truth
  - historical truth
  - inferred links
  - open conflicts

The user wants a much more serious knowledge graph, not just a correct but shallow one.

## Current Brainstack L2 Baseline

The current L2 already has:

- `graph_entities`
- `graph_relations`
- `graph_states`
- `graph_conflicts`
- state supersession tracking
- named-user alias merge over generic `User`
- current vs prior recall logic
- bounded provenance rendering

This means Phase 16 is not allowed to throw away or weaken:

- Phase 13 temporal correctness
- Phase 13 provenance behavior
- Phase 14/14.2 behavior correctness
- Phase 15 usefulness/ranking safeguards
- Brainstack as the single memory owner

## Confirmed Weak Spots

### 1. Relation discovery is too explicit

`graph.py` still depends heavily on explicit relation/state patterns.

That means the graph is strongest when the conversation literally says the relation.
It is much weaker when the link is only implied across multiple turns or multiple memories.

### 2. L2 retrieval is still too shallow

`search_graph()` mainly does lexical matching and row-type ordering.

That is not enough for a serious graph layer. Phase 16 needs a stronger L2 retrieval kernel that can surface the right graph facts, not just rows that textually match.

### 3. Recall packaging is still too flat

The read path still needs a clearer contract for graph truth classes:

- explicit current truth
- explicit historical truth
- inferred links
- stale/retired links
- open conflicts

Without that separation, good data can still feel weak or noisy when surfaced.

## Donor Position

Only narrow Mnemosyne ideas remain in scope for Phase 16.

Mnemosyne is useful only as inspiration for:

- tighter hybrid retrieval discipline
- compact local-store retrieval patterns
- simple temporal invalidation mindset

Mnemosyne is **not** a direct donor for:

- tool-heavy memory UX
- scratchpad ownership
- separate memory engine/runtime
- benchmark-first development

`keep` is explicitly out of scope.

## Hard Constraints

- no new memory runtime
- no new user-facing memory tool surface
- no scratchpad subsystem
- no benchmark chasing as development strategy
- no expanding Tier-1 heuristics to paper over L2 weakness
- must stay multilingual-safe by design
- must remain installer-carried and Brainstack-owned

## What Phase 16 Must Decide

1. What is the target L2 truth model?
   - exact separation between:
     - explicit truth
     - inferred links
     - stale/retired records
     - conflicts

2. What is the target L2 retrieval contract?
   - how graph facts are ranked
   - how current vs historical vs inferred evidence is packed
   - how confidence affects surfacing

3. How should bounded implicit relation discovery work?
   - not a second graph engine
   - not a giant heuristic list
   - not a benchmark toy
   - a Brainstack-owned candidate-link pipeline

4. What internal pieces can be replaced safely?
   - graph retrieval kernel
   - graph recall packing
   - weak connection finding

## Success Criteria

Phase 16 is successful if Brainstack gains:

- a stronger internal L2 truth model
- a stronger L2 retrieval path
- bounded implicit link discovery
- clearer recall packaging for graph evidence
- all of that without adding runtime sprawl, heuristic sprawl, or tool sprawl

## Recommended Effort

- `xhigh`
