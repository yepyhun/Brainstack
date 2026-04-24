# Phase 40 Context

## problem statement

The next blocker is no longer packet collapse, style-contract sanitization, append-safe operating storage, or typed graph ingress hardening.

The proven remaining problem is memory-authority divergence:

- nominal read surfaces can still trigger durable writes
- dirty historical state can remain active after the code path is hardened
- compiled policy, exact canonical recall, and ordinary-turn active lane can point at different effective truths
- transcript/profile style fragments can re-grow an authority-shaped fallback lane even after canonical repair
- operator debugging can still be contaminated by model introspection or by debug data sharing the same surface as the model-facing packet

This is a transaction-boundary and authority-convergence problem.

## why this is the correct next phase

- it closes the strongest remaining integrity bug class without broadening routing or graph semantics
- it stays donor-first because it tightens correctness and ownership seams rather than layering on new local intelligence
- it respects zero heuristic sprawl because the core move is boundary separation and authority lineage, not more cue logic
- it improves multimodal readiness because it strengthens typed ownership and proof surfaces rather than text-only special cases

## accepted sharpened reading

- the phase should be read as:
  - memory authority convergence
  - transaction boundary hardening
  - deterministic out-of-band proof
- the phase should not be read as:
  - a style-only fix
  - a new routing phase
  - a graph semantics phase
  - a broad profile/tier2 rewrite

## phase boundary

This phase should stay narrow around:

- explicit read vs write separation
- canonical generation repair and lineage control
- anti-regeneration for style authority
- compiled-policy / active-lane convergence
- out-of-band operator proof

This phase should not absorb:

- owner-first routing completion
- route-resolver redesign
- broad transcript/profile heuristic removal beyond what is required to stop style-authority regeneration
- graph value widening or multilingual claim-family expansion

Those remain real residuals, but they should not blur this integrity phase.

## expected proof shape

- a clean-store replay proves:
  - explicit teaching creates one active canonical generation
  - reset preserves exact recall
  - ordinary-turn lane points at the same authority lineage
- a dirty-store replay proves:
  - polluted active rows can be quarantined or superseded
  - stale style residue stops rebuilding authority
- a read-only replay proves:
  - recall and debug queries produce zero durable writes
- an operator proof proves:
  - Brainstack debug truth is available out-of-band
  - host/runtime layers are listed separately
  - the model no longer needs to narrate what Brainstack sent

## canonical principle reference

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`

## recommended model level

- `xhigh`
