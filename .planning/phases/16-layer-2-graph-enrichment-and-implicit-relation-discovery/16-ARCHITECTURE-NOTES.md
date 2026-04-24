# Phase 16 Architecture Notes

## Why Phase 16 Exists
- The current Brainstack Layer 2 is structurally correct, but still too weak for the intended product.
- Today L2 is strongest when the text explicitly says the relation or state.
- The user wants a much more serious knowledge graph, with stronger connection-finding and richer relation handling.

## Scope
- This is not a donor transplant phase.
- This is not permission to bolt on a second graph engine or second memory owner.
- This is a Brainstack-owned L2 deepening phase.
- This phase is broader than just \"write more L2 code\":
  - architecture review
  - retrieval-engine review
  - graph semantics review
  - bounded donor adaptation plan

## External Inspiration To Review
- `https://github.com/itsXactlY/neural-memory`
- `https://github.com/AxDSan/mnemosyne`

Use it only as inspiration for:
- implicit relation discovery
- connection-finding between memories that were not stated with an explicit relation phrase

Do not treat it as a direct implementation donor for:
- runtime architecture
- tool surface
- separate memory ownership
- separate recall/thinking subsystem

Mnemosyne should be reviewed mainly for:
- compact retrieval-engine design
- dense + keyword hybrid recall discipline
- simple temporal triple invalidation
- narrow, fast local-store patterns

Do not treat Mnemosyne as a direct implementation donor for:
- extra memory-tool surfaces
- scratchpad or note-first memory ownership
- skill-first personal memory handling
- benchmark-first product shaping

Keep is explicitly de-scoped from Phase 16.
Reason:
- it pulls the design toward a larger skill+notes platform shape
- that is not the direction wanted for Brainstack right now
- it is not needed for the current L2 strengthening decision

## Donor Adoption Plan

### What stays Brainstack-owned and is not replaced
- Phase 13 temporal/provenance contract stays Brainstack-owned.
- Brainstack remains the only live memory owner.
- The current 3-layer model stays:
  - L1 continuity/transcript
  - L2 graph/temporal truth
  - L3 corpus
- No donor replaces the host integration, installer path, or ownership boundaries.

### What is only inspiration, not direct carry-over

From Mnemosyne:
- LongMemEval score and benchmark posture
- tool-heavy memory UX
- scratchpad subsystem
- explicit memory command surface as the normal interaction model

### What is a likely Brainstack-side complement

From Mnemosyne:
- a tighter hybrid retrieval kernel for graph-related recall
- simpler, faster local-store access patterns where they improve L2 retrieval without changing ownership
- a cleaner split between hot/current graph facts and deeper historical graph evidence

### What may partially override current Brainstack internals

These are not donor transplants. They are candidate replacements for weaker current internals if Phase 16 confirms they are better:

- current L2 retrieval ranking logic may be replaced by a stronger hybrid ranking path
- current graph recall packing may be replaced by a cleaner explicit-vs-inferred separation
- current implicit-link discovery strategy may be replaced by a stricter candidate-link pipeline instead of today’s relatively weak connection finding

### What is genuinely new work for Brainstack
- explicit separation between:
  - explicit graph truth
  - inferred links
  - stale/retired links
  - conflicting links
- bounded implicit relation discovery that does not need a second graph engine
- confidence-aware graph recall policy
- stronger L2 retrieval without turning Brainstack into a tool-driven memory system

## Phase-16 Decision Rule For Mnemosyne

Use Mnemosyne as a source of narrow engine ideas only if they satisfy all of these:
- can live inside Brainstack as internal modules
- do not introduce new user-facing memory tools
- do not require scratchpad ownership
- do not turn development into benchmark-chasing
- improve real L2 recall or graph usefulness, not just synthetic scores

## Core Design Questions For Phase 16
- How should Brainstack distinguish:
  - explicit graph truth
  - inferred links
  - uncertain candidate links
  - conflict and supersession behavior
- How should implicit relation discovery stay bounded so it does not explode token use or graph noise?
- Which signals should be allowed for implicit links:
  - semantic similarity
  - co-reference / shared entities
  - repeated co-occurrence across sessions
  - continuity summary overlap
  - corpus overlap
- How should inferred links surface during recall:
  - always hidden unless useful
  - shown with confidence
  - separated from explicit truth
- How should L2 remain update-safe and modular instead of turning into a god object?

## Hard Constraints
- No second runtime
- No separate graph owner
- No uncontrolled background complexity
- No donor-architecture transplant
- No token-budget collapse
- Must remain compatible with the existing 3-layer Brainstack model
