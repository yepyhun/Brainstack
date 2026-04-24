# Phase 51 Implementation Contract

## invariant

This phase must judge the Brainstack-Hermes integration honestly. It must not turn into design defense, feature planning, or benchmark-shaped self-justification.

## canonical principle reference

Use the canonical principles file directly:
- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`

Pinned names that must govern this phase:
- `Donor-first`
- `Modularity / Upstream updateability`
- `Fail-closed upstream compatibility`
- `No benchmaxing`
- `Truth-first / no "good enough"`
- `Zero heuristic sprawl`
- `Multimodal-first architecture`
- `The donor-first elv marad`

## required properties

- the audit must use the full code graph on `/home/lauratom/Asztal/ai/finafina`
- the audit must include runtime seam evidence, not graph evidence alone
- `MemoryManager` thinness and host blast radius must both be judged
- Brainstack plugin visibility or invisibility in the graph must be treated as a first-class finding
- passing tests are supporting evidence only
- the final verdict must explicitly separate:
  - runtime seam fit
  - inspectability / maintainability fit
  - product-value fit

## prohibited outcomes

- concluding “synergy” from green tests alone
- ignoring graph invisibility because the plugin seems to work locally
- hiding plugin size or decomposition debt behind the correct plugin seam
- weakening findings to avoid creating follow-up work
- turning this audit into a feature roadmap without first stating the verdict

## required verification artifact

Produce one audit artifact that records:
- graph build stats
- architecture overview stats
- host hub / bridge findings relevant to memory integration
- memory seam runtime findings
- Brainstack plugin inspectability findings
- explicit final verdict
- concrete donor-fit gap map

## recommended model level

`xhigh`
