# Phase 31 Context

## problem statement

After `30.5` and `30.6`, the live product can still feel worse than before in the exact flow the user cares about:

- provider auth incidents happened and confused the test window
- after auth recovered, ordinary replies still violated the communication rules
- asking for the full `29` rules triggered `session_search`
- after the user pasted the full rule pack, the runtime attempted `skill_manage` instead of staying inside Brainstack

This is no longer well-described as a generic memory failure. The current evidence points to a stricter authority layer sitting on top of bad canonical truth and inconsistent host tool blocking.

## why this is the correct next phase

The next hotfix should not be guessed. The current live behavior mixes:

- canonical truth quality
- admission/convergence quality
- host runtime execution-path quality

Freezing one accepted root-cause reading first prevents another bundled patch set that improves one seam while leaving the actual breakpoints untouched.

## accepted sharpened reading

- the live active canonical behavior contract can be partial and still remain authoritative
- the partial canonical revision can be written by weaker `tier2_llm` admission
- explicit user multi-message rule teaching does not yet converge into one committed canonical revision
- Brainstack-only tool blocking exists, but it is not guaranteed on every execution path
- `session_search` is still reachable as a personal-memory fallback in practice

## phase boundary

This phase is not allowed to drift into:

- broad behavior-memory redesign
- broad control-plane redesign
- general graph/runtime cleanup unrelated to the proven regression path

## canonical principle reference

- [IMMUTABLE-PRINCIPLES.md](../../IMMUTABLE-PRINCIPLES.md)

## expected proof shape

The closing proof for this phase should look like this:

1. A session trace shows the exact failing live behavior.
2. A DB read shows the active canonical contract is partial or otherwise wrong in a way that explains the trace.
3. A code-level seam shows why multi-message rule teaching failed to converge.
4. A code-level seam shows whether Brainstack-only blocking is uniform or half-applied.
5. The final root-cause reading is compact, evidence-backed, and directly usable as the hotfix scope.

## recommended model level

- `xhigh`
