# Phase 59 Hard Gates

Phase 59 is not complete unless all of the following are true.

## 1. Attribution gate

- there is explicit evidence showing the contribution of:
  - Hermes host system prompt
  - builtin memory / user-profile surfaces
  - Brainstack system-prompt block
  - Brainstack prefetch packet
  - tool schema overhead
  - conversation history
- the phase does not flatten these into one number and call it “Brainstack”

## 2. Allocator gate

- Brainstack no longer relies only on fragmented per-shelf caps for the tested paths
- there is one explicit cross-shelf allocation decision surface
- the packet gets smaller by selection quality, not by blind amputation

## 3. Fusion gate

- hybrid retrieval fusion is measurably more coherent than before
- keyword and semantic channels both remain usable
- no query-specific heuristic farm is introduced

## 4. Product-quality gate

- token pressure improvement is demonstrated on installed runtime paths
- retrieval usefulness does not materially regress on the covered product flows
- canonical profile / continuity / graph / corpus recall still behaves correctly

## 5. Source-of-truth gate

- all changes originate in:
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`
- all claimed behavior is reproduced on:
  - `/home/lauratom/Asztal/ai/finafina`

## 6. Truth-first gate

The final result must be able to say one of these explicitly:

- Brainstack was not the dominant context-pressure source; the improvement is partial but real
- Brainstack was a major contributor; the improvement is direct and measured

Anything weaker than that fails the attribution requirement.
