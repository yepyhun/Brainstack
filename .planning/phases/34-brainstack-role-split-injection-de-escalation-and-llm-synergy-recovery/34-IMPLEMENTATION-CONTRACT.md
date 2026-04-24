# Phase 34 Implementation Contract

## invariant

Brainstack must become more synergistic with the LLM by narrowing routine behavior governance while preserving durable memory, continuity, and explicit high-value invariants.

## required implementation properties

- the implementation must explicitly separate:
  - archival / exact behavior recall
  - narrow ordinary-turn invariant support
  - factual continuity / identity / task / graph truth support
- ordinary-turn injection must become less intrusive by default
- any always-on invariant lane must be:
  - smaller than the canonical behavior contract
  - objectively checkable where feasible
  - justified by product value, not by obedience vanity
- the memory-context framing must stop over-claiming authority over local conversation where that authority is not actually needed
- authority wording must be proportional to guarantee:
  - no strong “non-optional” style-governor framing for behavior material that is still budget-limited or only partially enforced
- durable factual truth must remain strong and truthful
- the result must be a better second-brain kernel, not just a weaker one
- any retained always-on invariant lane must be small, explicit, and justified by product value
- the phase must remain donor-first and upstream-friendly

## prohibited outcomes

- broad new behavior heuristic farms
- replacing the LLM’s local reasoning with stronger Brainstack prompt governance
- deleting Brainstack memory support to make the assistant “feel freer”
- hiding regressions behind benchmark-shaped or transcript-shaped demos
- adding another shadow owner for behavior or continuity truth
- solving the problem by shrinking evidence channels while leaving oversized behavior authority untouched

## likely implementation seams

- `brainstack/control_plane.py`
- `brainstack/retrieval.py`
- `brainstack/executive_retrieval.py`
- `brainstack/behavior_policy.py`
- `brainstack/output_contract.py`
- `agent/memory_manager.py`
- only the minimal `hermes-final` host seams needed to preserve the new role split at runtime
- any rendering or host wording seams that currently make behavior packets sound more authoritative than their real enforcement path

## verify contract

- prove that the ordinary-turn memory payload is narrower and more role-appropriate
- prove that durable truth recall still works
- prove that natural conversational turns are less likely to be derailed by Brainstack’s own injected behavior payload
- prove that exact canonical behavior recall remains available without requiring large always-on behavior injection
- prove that the model is not being starved of live evidence in order to make the reduced hot path look cleaner
- prove parity on:
  - source
  - `hermes-final`
  - rebuilt live runtime

## canonical principle reference

- [IMMUTABLE-PRINCIPLES.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md)

## recommended model level

- `xhigh`
