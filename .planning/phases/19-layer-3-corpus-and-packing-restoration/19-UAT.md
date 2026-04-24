# Phase 19 UAT

## Verdict

Phase 19 verify passes.

## User-facing verification outcome

### 1. Corpus recall is materially stronger on larger prior material

User verdict: `pass`

This was explicitly called out by the user as the most important feature in the whole memory kernel.

Accepted interpretation:

- when the question relates to an older document, larger prior material, or previously linked content
- the system should not only return keyword fragments
- it should surface materially more relevant passages
- and that should make the answer more useful, not just more “retrieval-like”

### 2. The semantic corpus leg is genuinely live

User verdict: `pass`

Accepted interpretation:

- Phase 19 is not allowed to fake semantic retrieval with the old lexical path
- the results should stay meaningfully related even when the question wording changes
- richer corpus recall is accepted as real semantic improvement, not only a backend swap

### 3. Stronger corpus recall stays usable

User verdict: `pass`

Accepted interpretation:

- broader recall is acceptable and even preferred over dropping something important
- but the answer must remain coherent
- Phase 19 is therefore considered successful only if the stronger corpus path does not collapse into an unusable dump

### 4. The L3 improvement matters in ordinary conversation too

User verdict: `pass`

Accepted interpretation:

- the Layer 3 restoration is considered proven only if it helps in normal conversation
- not only in obvious “document retrieval” prompts
- so the stronger corpus path is treated as a genuine agent improvement, not a backend-only win

## Technical proof

- bounded Phase 19 eval ladder passes the fast gates
  - Gate A: `4 passed`
  - Gate B: `2 passed`
  - Gate C: explicit skip without `COMET_API_KEY` / `COMETAPI_API_KEY`
- extra targeted regression suite passes
  - `tests/test_install_into_hermes.py`
  - `tests/test_brainstack_graph_backend_kuzu.py`
  - `7 passed`
- syntax compile passes for touched source, tooling, and test files

## Runtime carry-through status

- source-side execution is complete
- no live Bestie carry-through was forced in this phase
- no rebuild was forced
- no push was performed

This is intentional under the current workflow rule: rebuild is reserved for bounded runtime proof, not for every source-side recovery execute/verify step.

## What Phase 19 is considered to have proven

- Layer 3 now has a real embedded semantic corpus backend seam instead of relying on the old SQLite-only corpus path as the effective center
- the shell-side journal now coordinates both graph and corpus publish targets
- the L1 semantic corpus leg is genuinely live through the existing executive retrieval contract
- stronger corpus recall is visible in practical usage, not only in technical tests
- packing remained bounded and usable instead of becoming a cosmetic rescue layer

## What remains intentionally open

- final end-to-end restoration proof across the full recovered stack
- any heavier benchmark/final-boss evaluation reserved for the later verdict phase
- final source push only after the remaining recovery track is genuinely complete
