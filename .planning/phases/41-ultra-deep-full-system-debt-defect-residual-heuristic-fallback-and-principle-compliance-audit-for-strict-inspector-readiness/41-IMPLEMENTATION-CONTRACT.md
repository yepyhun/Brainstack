# Phase 41 Implementation Contract

## invariant

This phase must increase truthfulness, not apparent confidence.

## canonical principle reference

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`
- pinned names:
  - `Donor-first`
  - `Fail-closed upstream compatibility`
  - `Truth-first / no "good enough"`
  - `Zero heuristic sprawl`
  - `Multimodal-first architecture`

## required properties

- every finding must be backed by a file path, runtime log, or deterministic reproduction
- findings must distinguish:
  - source defect
  - runtime drift
  - deploy/config debt
  - bounded residual
  - already-fixed historical issue
- principle compliance must be judged against the immutable principles file directly
- incremental findings must be written to durable artifacts during the audit

## prohibited outcomes

- vague “there may be issues” summaries
- merging multiple issue classes into one fuzzy note
- claiming full compliance without checking source and runtime proof
- hiding residual heuristics because they are legacy
- using the model's own narration as evidence

## required audit artifact

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/41-ultra-deep-full-system-debt-defect-residual-heuristic-fallback-and-principle-compliance-audit-for-strict-inspector-readiness/41-AUDIT-LOG.md`

## recommended model level

- `xhigh`
