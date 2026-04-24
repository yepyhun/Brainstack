# Phase 32 Context

## problem statement

The current live regression is no longer abstract:

- the active canonical behavior contract can be partial
- the system can still recall only a cut-off subset of the rules
- the user can paste the missing rules and still not get one durable canonical update
- the host can still take a side-memory detour through `skill_manage`

That is a production hotfix problem, not just a planning discussion.

## why this is the correct next phase

Phase `31` exists to freeze the accepted root-cause model. Once that is done, the next action should be a narrow hotfix on the seams that actually broke:

- canonical contract protection
- multi-message convergence
- sequential-path tool blocking

Anything broader would slow the fix down and blur accountability.

## phase boundary

This phase is not responsible for:

- redesigning the whole behavior-policy architecture again
- solving every routing heuristic in the product
- solving unrelated provider/auth incidents

## accepted sharpened reading

- stronger authority without stronger admission can make the product feel worse
- a bad canonical revision is more damaging than a fuzzy partial recall path
- host/runtime guardrails only count if they are wired uniformly on every execution path

## canonical principle reference

- [IMMUTABLE-PRINCIPLES.md](../../IMMUTABLE-PRINCIPLES.md)

## expected proof shape

The closing proof for this phase should look like this:

1. The user can teach a long rule pack across multiple messages and get one committed canonical revision.
2. A weaker Tier-2 style-contract write cannot supersede that revision.
3. Asking for the full rules recalls the canonical contract or fails closed explicitly.
4. `skill_manage` personal-memory detours are blocked in both sequential and concurrent paths.
5. The same live-style scenario no longer collapses into partial recall plus side-tool misuse.

## recommended model level

- `xhigh`
