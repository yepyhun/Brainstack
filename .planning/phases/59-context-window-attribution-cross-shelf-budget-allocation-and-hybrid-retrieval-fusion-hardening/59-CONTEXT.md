# Phase 59 Context

## why this phase exists

The next serious product complaint is now quality/efficiency shaped rather than runtime-breakage shaped:

- users report that Hermes fills the context window quickly
- Brainstack is the active memory provider
- it is therefore tempting to blame Brainstack directly

That would be too sloppy.

The installed runtime now makes it clear that context pressure is a whole-stack problem:

- Hermes host guidance is already large
- builtin memory and user-profile surfaces are always present
- Brainstack adds both a system-prompt projection and a per-turn prefetch packet
- tool schemas and conversation history can dwarf all of that on some turns

This phase exists because we need to answer the attribution question honestly first, then fix the Brainstack-owned part of the problem in the highest-leverage way.

## accepted diagnosis

- the main remaining opportunity is not a new memory lane
- it is not a new donor
- it is not a vector-backend swap
- it is not a prompt hack

The real opportunity is:

1. better cross-shelf allocation
2. better hybrid retrieval fusion
3. better attribution of prompt growth

That is donor-first and product-first.

## current evidence summary

### host-side pressure is real

The installed runtime currently includes large prompt-builder guidance blocks before Brainstack packetization is counted.

Measured character lengths on the installed runtime include:

- `MEMORY_GUIDANCE`: ~4597
- `USER_PROFILE_GUIDANCE`: ~3248
- `TOOL_USE_ENFORCEMENT_GUIDANCE`: ~1419
- `OPENAI_MODEL_EXECUTION_GUIDANCE`: ~3176 when applicable
- live `USER.md`: ~790

This alone is enough to show that quick context fill is not a pure Brainstack story.

### Brainstack still contributes materially

Brainstack contributes on two surfaces:

1. provider system-prompt block
2. provider prefetch packet injected into the current turn

And its current allocation logic is only partially unified:

- route-aware policy exists
- per-shelf budgets exist
- there is still no one strong cross-shelf allocator

### current plugin-side budget defaults

- `profile_match_limit = 4`
- `transcript_char_budget = 560`
- `graph_match_limit = 6`
- `corpus_match_limit = 4`
- `corpus_char_budget = 700`

These are bounded, but not yet globally optimized.

## why this is not just an L3 issue

The problem is not only corpus retrieval.

If it were only L3, the obvious answer would be:

- compress semantic retrieval harder
- or swap Chroma for a faster/smaller ANN backend

But the verified stack shows the pressure is broader:

- host prompt guidance
- builtin memory and user profile
- Brainstack profile / continuity / graph / corpus selection
- tool schemas
- message history

So the right first move is not an L3 backend swap. It is attribution plus allocation.

## design intent for the two improvements

### cross-shelf allocator

The allocator must answer:

- what survives into the packet
- what gets dropped first
- how profile/continuity/graph/corpus compete
- how route intent changes the budget split

The goal is not to inject less at all costs. The goal is to inject the smallest useful evidence set.

### hybrid retrieval fusion

The fusion must answer:

- when keyword evidence should dominate
- when semantic evidence should dominate
- when both should combine
- how to avoid over-admitting weak candidates that later waste packet space

This is retrieval quality work, not just latency work.

## non-goals

- this phase does not claim that Brainstack alone created the context problem
- this phase does not reopen behavior-governor ideas
- this phase does not reframe MemPalace donor intent
- this phase does not assume a new vector backend is the main answer

## source-of-truth rule

- code source of truth:
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`
- install-and-proof target:
  - `/home/lauratom/Asztal/ai/finafina`

Any claimed improvement must be authored in the source repo and reproduced on the installed runtime.
