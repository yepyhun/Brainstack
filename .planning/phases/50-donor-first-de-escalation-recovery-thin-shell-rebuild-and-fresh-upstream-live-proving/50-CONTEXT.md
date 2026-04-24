# Phase 50 Context

## why this phase exists

The project drifted from its main goal.

The intended system is a three-layer orchestration shell:
- donor layers do the real memory work
- the shell coordinates them
- the shell enforces ownership and consistency boundaries

The recent recovery work improved several correctness seams, but the product also drifted into a host-level rule-governance shape:
- ordinary chat became dependent on output blocking
- generic safe fallback replies became user-visible behavior
- the host started acting like the main behavior engine instead of a thin donor-supporting shell

That is the wrong product.

This phase corrects that by stepping back to fresh upstream Hermes and rebuilding only the minimum donor-first shell.

Important clarification:
- the target is not to make the system less intelligent
- the target is to move intelligence back to the right place
- donor/provider memory intelligence should remain
- host-level rule governance over ordinary chat should not

## strategic reading

The problem is no longer just “bugs in a mostly-correct architecture.”

The deeper problem is architectural inversion:
- the shell became too thick
- chat quality now depends on the shell’s rule machinery
- donor orchestration is no longer the obvious center of gravity

The fix must therefore be subtraction first:
- remove
- simplify
- re-center

But the subtraction target is specific:
- subtract host control
- not donor intelligence

Only after the simplification is mostly done should the live test loop begin.

## fresh baseline

New recovery baseline:
- repo: `/home/lauratom/Asztal/ai/finafina`
- remote: `https://github.com/NousResearch/hermes-agent`
- branch: `main`
- current head at planning time: `2cdae233e2a869656b194baa9be0bc6eef6d988f`

This matters because the old install tree and live profile were already carrying:
- runtime drift
- historical state corruption
- partial corrective overlays

The cleanest way to recover a working product is to rebuild from the fresh upstream baseline instead of continuing to patch the drifted path.

## architectural target

Wanted end state:
- Hermes remains the host
- donor memory providers remain the memory workers
- Brainstack becomes a thin memory-orchestration shell
- native host files stay thin and upstream-friendly
- ordinary chat stays chat-first
- memory intelligence stays donor-first

Not wanted:
- host-level behavior-policing engine
- memory shell turning into final-output governor for ordinary chat
- broad prompt/rule system that overrides ordinary conversational flow
- patch accumulation that hides the original product shape

## keep / move / remove reading

### keep
- provider-side memory intelligence
- ownership and truth boundaries
- cross-store coordination and consistency
- donor-aligned recall and write semantics

### move
- any remaining memory-specific “smart” reply-path logic out of generic host delivery and behind provider or memory-manager seams

### remove
- host-level hard gating for ordinary replies
- generic blocker fallback replies
- chat-path dependence on Brainstack output enforcement
- shell logic that acts like a second behavior engine

## live-proof philosophy

The live proof should happen late in the phase, not at the beginning.

Reason:
- if we start with live patch loops too early, we will just keep rescuing the overbuilt architecture
- the bulk of the work must be subtraction and simplification first

So the phase intentionally ends with:
- a fresh runtime/profile setup
- a realistic live proof pack
- a rolling rethink loop only for bounded shell-level corrections

## failure criteria

The phase has failed if it ends with any of these:
- ordinary chat still depends on host-level Brainstack blocked/fallback machinery
- the shell still behaves like a second behavior engine
- the fresh-upstream baseline is abandoned in favor of reviving the old drifted path
- the final result is “more patches” instead of a simpler product
