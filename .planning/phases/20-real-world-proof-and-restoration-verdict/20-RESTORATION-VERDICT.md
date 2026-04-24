# Phase 20 Restoration Verdict

## Verdict

`mixed / corrective phase required`

The donor-first recovery track materially improved the real system, but it did **not** earn a full `restored` verdict.

## Why It Is Not `restored`

The final-boss benchmark was executed through the real Brainstack path and did **not** materially improve over the pre-recovery baseline.

Evidence:

- pre-recovery Brainstack LongMemEval subset:
  - `3 / 15`
  - `0.20`
- Phase `20` final-boss Brainstack LongMemEval subset:
  - `3 / 15`
  - `0.20`

The pass/fail mix changed on a couple of questions, but the end result stayed flat.

That means a full restoration claim would be dishonest.

## What Did Pass

### Stream A. Isolated L1 smartening proof

Pass.

The new proof harness shows that `L1` smartening can be isolated from graph and corpus contribution.
The system can still carry the important thread through continuity + temporal + keyword behavior when graph and corpus are explicitly disabled.

### Stream B. Everyday graph usefulness proof

Pass.

The graph delta is attributable above the isolated `L1` baseline.
Everyday connected reasoning got better without knocking current truth off the front.

### Stream C. Everyday corpus usefulness proof

Pass.

The corpus delta is attributable above the non-corpus baseline.
The semantic corpus leg is genuinely live and improves real reuse of larger prior material.

### Stream D. Cross-store consistency proof

Pass.

The shell + `Kuzu` + `Chroma` stack now has working publish-journal evidence and readable degraded behavior.
The combined stack does not collapse into chaos when a donor backend is unhealthy.

### Stream E. Restored gate reruns

Pass.

The bounded gates from `17`, `18`, and `19` still pass after assembly:

- Phase `17` Gate A: pass
- Phase `17` Gate B: pass
- Phase `18` graph regression checks: pass
- Phase `19` Gate A: pass
- Phase `19` Gate B: pass

### Stream F. Final-boss benchmark proof

Executed successfully, but failed to support a full restoration verdict.

The benchmark result stayed flat against the earlier `3 / 15` baseline.

## Benchmark-Exposed Failure Shape

The strongest repeated failure families in the final-boss run were:

- temporal ordering / date-gap reasoning
- multi-session aggregation of details and counts
- missing exact specific detail recall
- some preference/detail cases still collapsing into generic advice or generic knowledge
- occasional irrelevant memory contamination in the final recalled context

This is enough to block a full restoration claim even though the cheaper real-world proof streams improved.

## Recorded Corrective Diagnosis

The post-execute diagnosis is now explicitly captured for `Phase 20.1`.

The benchmark-exposed fidelity gap is currently understood as four concrete problems:

1. conversational history is still too semantic-blind
2. temporal evidence is not rendered explicitly enough for ordering-heavy questions
3. legacy graph ingress still allows junk truth rows into graph context
4. flat shallow trimming can cut off answer-bearing exact details

See:

- [20.1-ARCHITECTURE-NOTES.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.1-benchmark-exposed-memory-fidelity-recovery/20.1-ARCHITECTURE-NOTES.md)

## Honest Interpretation

The recovery track succeeded at:

- restoring the intended donor-first architecture
- improving everyday usefulness
- making the three layers work together coherently

But it did **not yet** succeed at:

- turning that recovery into donor-level final-boss memory fidelity

So the correct interpretation is:

- stronger real system than the diluted pre-recovery state
- but not yet strong enough to say the original `big 3 + thin glue` ambition is fully restored

## Routing Decision

Route to corrective follow-up:

- `Phase 20.1`

The purpose of that corrective phase is to close the benchmark-exposed fidelity gap without collapsing back into benchmark gaming, heuristic drift, or donor-architecture rollback.

## Post-20.1 Rerun Update

After `20.1` completed and a fresh final-boss rerun was executed on the real Brainstack path, the benchmark improved from `3 / 15` to `9 / 15`.

That rerun materially changes the diagnosis:

- the donor-first recovery direction is working
- the remaining blocker is better described as a targeted exact-fact conversational retrieval gap
- the next corrective route should therefore focus on retrieval precision, decomposition where truly needed, packing fidelity, and update-priority rather than reopening the broad architecture question

This recorded update does **not** automatically upgrade the original `Phase 20` verdict to `restored`.
It does tighten the next routing decision from broad fidelity repair to high-precision conversational fact-retrieval recovery.

## Post-20.2 Forensics Update

The first `20.2` corrective bundle was then executed and rerun on the same real Brainstack path.

That rerun regressed from:

- post-`20.1`: `9 / 15`
- post-`20.2`: `7 / 15`

This does **not** reopen the original architecture verdict.
It means something narrower:

- the donor-first recovery track is still the correct broad architecture
- but the first exact-fact corrective bundle mixed together at least one harmful retrieval lever with several real local fixes

Therefore the recorded next step after `20.2` is now:

1. pure split-pass regression forensics with `query_decomposer=None`
2. only then bonus ablation if needed
3. only after those results, decide what remains architectural rather than bundled-regression noise

This keeps the `Phase 20` verdict honest:

- still not `restored`
- not rolled back to “architecture was wrong”
- now narrowed further to regression forensics plus later retrieval-mode refinement
