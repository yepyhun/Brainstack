# Phase 20 Context

## Discuss Outcome

Phases `17`, `18`, and `19` restored the intended donor-first shape of the three memory layers:

- `L1`: Hindsight/TEMPR-style executive retrieval
- `L2`: Graphiti-shaped graph/truth retrieval on embedded `Kuzu`
- `L3`: MemPalace-shaped raw corpus retrieval on embedded `Chroma`

The remaining question is no longer architectural direction.
The remaining question is whether the assembled system is now genuinely closer to the original `big 3 + thin glue` ambition, or whether it is still only a more elaborate custom Brainstack.

Phase `20` exists to answer that question with hard evidence and a hard verdict.

## Why This Phase Exists

The project explicitly rejected two weak endings:

1. “it is better than before, so close enough”
2. “the architecture sounds right, so we can assume it is restored”

The user’s standard is not MVP and not partial credit.
The recovery track must prove that the donor-first vision was materially restored in real use.

## Original Standard To Judge Against

The correct comparison point is the original ambition:

- three world-class memory kernels
- each contributing its real strength
- Brainstack acting as thin shell rather than replacement brain
- the combined system feeling stronger end to end than the diluted pre-recovery version

Phase `20` must judge against that standard.
It may not judge against the weaker “it no longer crashes” baseline.

## What Must Be Proved

Phase `20` must prove all of the following:

1. `L1` really makes the agent feel smarter in normal conversation, not just more recall-heavy
2. `L2` makes everyday connected reasoning better, not just graph demos prettier
3. `L3` makes larger prior material genuinely reusable, not just searchable
4. the assembled stack remains coherent when more than one donor-backed store is active
5. the restored system is not only more complex, but substantively stronger

## Evidence Classes

The proof must combine multiple evidence classes:

- real conversational use
- bounded source-side eval ladders from `17`, `18`, and `19`
- cross-store resilience and consistency checks
- one final heavier benchmark-style gate through the real Brainstack path

No single class is enough on its own.

Important attribution rule:

- the proof must separate `L1`-only smartening evidence from graph-driven and corpus-driven gains
- otherwise a mixed verdict cannot route cleanly to the right corrective layer

## Hard Rule: Benchmark Is A Verdict Input, Not The Goal

Benchmark evidence is allowed and required at the end.
Benchmark chasing is still forbidden.

That means:

- no benchmark-specific heuristics
- no prompt/gamey tuning for the final run
- no claiming restoration purely from benchmark numbers
- no skipping the final benchmark after strong subjective proof

The benchmark is the last confirming or falsifying gate, not the first design driver.

## Hard Rule: Evidence Streams Must Be Attributable

Phase `20` must not use overlapping proof streams that blur layer ownership.

That means:

- Stream A must isolate `L1` executive smartening without graph or corpus contribution
- Stream B must prove graph usefulness as a delta above that isolated baseline
- Stream C must prove corpus usefulness as a delta above a baseline where corpus contribution is disabled

If the proof cannot say which layer actually produced the gain, the verdict is not hard enough.

## Hard Rule: No Hidden Redesign Inside Phase 20

Phase `20` is a proof-and-verdict phase, not another restoration phase.

Allowed:

- bounded correctness fixes that block honest proof
- proof harness work
- evidence collection
- explicit verdict writing

Not allowed:

- new donor architecture resets
- hidden rewrites of `L1`, `L2`, or `L3`
- benchmark-driven behavior changes
- “just one more feature” drift

If proof finds a real blocker, the phase must open a corrective follow-up rather than smuggling a redesign into the verdict phase.

## Cross-Store Reality Check

This is the first phase that must judge the recovered stack as a whole:

- shell state in `SQLite`
- graph truth in `Kuzu`
- corpus semantics in `Chroma`

So the phase must explicitly look at:

- pending vs published consistency
- replay after interruption
- degraded but non-chaotic read behavior when a donor backend is unhealthy
- whether the combined system still answers coherently while those protections exist

## Verdict Standard

The phase must end with one of these explicit outcomes:

1. restored
2. mixed / not yet restored, corrective phase required
3. not restored

There is no acceptable vague outcome like “better overall”.

## Recommended Effort

`xhigh`
