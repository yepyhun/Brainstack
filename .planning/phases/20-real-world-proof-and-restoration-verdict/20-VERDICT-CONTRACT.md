# Phase 20 Verdict Contract

## Purpose

This contract prevents Phase `20` from collapsing into either:

- benchmark theater
- architectural storytelling without proof

It forces a hard, evidence-backed restoration verdict.

## Required Evidence Streams

### Stream A. Everyday smartening proof

Required output:

- bounded multi-turn conversations showing that the recovered `L1` carries the important thread better
- evidence that relevant prior material is surfaced because it helps, not because it merely matches keywords
- proof that the agent feels more intelligent, not just more memory-heavy
- proof harness configuration with graph and corpus contribution explicitly disabled or capped to zero for this stream

Hard rule:

- this stream fails if the evidence is mainly memory restatement instead of better continuation
- this stream fails if graph or corpus channels are still materially contributing, because then the gain is not attributable to `L1`

### Stream B. Everyday graph usefulness proof

Required output:

- normal-language scenarios where connected truths and relations help the answer materially
- proof that current truth remains primary while connected context becomes richer
- delta evidence relative to the Stream A baseline, so graph-driven gain is attributable to `L2`

Hard rule:

- this stream fails if graph usefulness is only visible in contrived “graph demo” prompts
- this stream fails if it reuses a blended proof where graph contribution cannot be separated from general `L1` smartening

### Stream C. Everyday corpus usefulness proof

Required output:

- scenarios where larger prior material is reused across turns
- proof that semantic retrieval and raw corpus reuse materially help answer quality
- evidence that broader recall remains usable rather than chaotic
- delta evidence relative to a baseline where corpus contribution is disabled, so corpus-driven gain is attributable to `L3`

Hard rule:

- this stream fails if corpus usefulness still depends mainly on lexical fallback or packing cosmetics
- this stream fails if the proof cannot distinguish corpus contribution from already-present graph or continuity effects

### Stream D. Cross-store consistency proof

Required output:

- publish journal evidence across shell state plus active donor stores
- proof of:
  - pending vs published visibility
  - replay after interruption
  - idempotent publication
  - readable degraded behavior when a backend is unhealthy

Hard rule:

- this stream fails if the combined stack only looks good when all stores are perfectly healthy and synchronized

### Stream E. Restored gate reruns

Required output:

- bounded reruns of the meaningful gates from Phases `17`, `18`, and `19`
- explicit pass/fail record for each gate family

Hard rule:

- the final verdict may not ignore a regression in an already-restored layer

### Stream F. Final-boss benchmark proof

Required output:

- one bounded heavier benchmark-style run through the real Brainstack path
- clear record of:
  - provider/model path
  - memory path
  - result
  - interpretation

Hard rule:

- the benchmark may support or block the verdict
- it may not define the architecture
- no benchmark-specific heuristics may be introduced for this stream

## Protected Boundaries

### No hidden redesign

- `20` may fix bounded blockers to honest proof
- `20` may not smuggle in fresh donor-restoration work

### No benchmark gaming

- no question-specific heuristics
- no prompt surgery aimed only at the final benchmark
- no donor-shape regression in exchange for a prettier score

### No soft verdict

- “better than before”
- “good enough”
- “close enough to ship”

None of these are acceptable final outcomes.

## Verdict Rules

### Restored

Allowed only if:

- all required evidence streams are materially positive
- no restored layer meaningfully regressed
- the combined system feels substantively stronger, not merely larger
- the final benchmark does not materially contradict the real-world evidence

### Mixed / corrective phase required

Required if:

- some streams are strong but at least one important stream still falls short
- or the final benchmark materially undercuts a full-restoration claim
- or proof exposes a blocker that needs another focused phase

### Not restored

Required if:

- the combined system still does not deliver the original donor-first ambition in substance
- or the proof only supports “more complex, somewhat better” instead of real restoration

## Routing Rule

- `restored` -> milestone closeout or next milestone planning
- `mixed / corrective phase required` -> insert corrective recovery phase before closeout
- `not restored` -> do not close the milestone; route to corrective planning explicitly
