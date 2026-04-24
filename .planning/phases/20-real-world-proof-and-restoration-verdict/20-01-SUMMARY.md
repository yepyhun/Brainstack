# Phase 20 Summary

## Outcome

Phase `20` executed the final proof-and-verdict pass for the donor-first recovery track.

This phase did not introduce another architecture reset.
Instead, it built the proof harness, ran the required evidence streams, executed the final-boss benchmark through the real Brainstack path, and wrote the restoration verdict.

The result is:

- `mixed / corrective phase required`

## Source Changes

- added bounded Phase `20` proof tests:
  - [test_brainstack_phase20_proof.py](/home/lauratom/Asztal/ai/atado/Brainstack/tests/test_brainstack_phase20_proof.py)
- added bounded Phase `20` eval ladder:
  - [run_brainstack_phase20_eval_ladder.py](/home/lauratom/Asztal/ai/atado/Brainstack/scripts/run_brainstack_phase20_eval_ladder.py)
- Phase `20` final-boss benchmark report written locally at:
  - [brainstack-final-boss.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase20/brainstack-final-boss.json)

## Validation

### Stream A / attribution proof

- `tests/test_brainstack_phase20_proof.py`
- result: `5 passed`

### Stream E / restored gate reruns

- Phase `17` Gate A:
  - `4 passed`
- Phase `17` Gate B:
  - `26 passed`
- Phase `18` bounded regression selection:
  - `2 passed`
- Phase `19` Gate A:
  - `6 passed`
- Phase `19` Gate B:
  - `2 passed`

### Stream C / integrated conversational proof

- bounded `tests/test_brainstack_real_world_flows.py` selection
- result: `4 passed`

### Stream D / cross-store degraded proof

- bounded `cross_store` selection from `tests/test_brainstack_phase20_proof.py`
- result: `2 passed`

### Stream F / final-boss benchmark

- real Brainstack/Hermes path
- sample size: `15`
- result:
  - `3 / 15`
  - `0.20`
  - provider: `cometapi`
  - model: `minimax-m2.7`
  - elapsed: `407.384s`

### Benchmark comparison against pre-recovery baseline

- pre-recovery:
  - `3 / 15`
  - `0.20`
- Phase `20`:
  - `3 / 15`
  - `0.20`

Net result:

- no material benchmark improvement

## Result

Phase `20` proves that:

- the recovered system is materially stronger in bounded real-world evidence than the diluted pre-recovery stack
- the donor-first architecture now behaves coherently across `SQLite`, `Kuzu`, and `Chroma`
- but the benchmark-exposed memory fidelity gap is still real

So the recovery track is **not** ready for milestone closeout.

The correct final status is:

- `mixed / corrective phase required`

See:

- [20-RESTORATION-VERDICT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20-real-world-proof-and-restoration-verdict/20-RESTORATION-VERDICT.md)

## Follow-up

- do not claim full restoration
- do not close the milestone yet
- route to `Phase 20.1`
- keep the focus on benchmark-exposed fidelity gaps:
  - temporal ordering
  - multi-session aggregation
  - exact detail carry-through
  - irrelevant recall contamination
