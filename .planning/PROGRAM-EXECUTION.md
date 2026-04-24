# Program Execution

## Objective

Execute Hermes Brainstack as a GSD-style program rather than as an ad hoc plugin experiment.

## Program Shape

The delivery is split into four waves:

1. Foundation
2. Memory Substrate
3. Control And Displacement
4. Operational Integration

## Non-Negotiable Product Rules

1. Hermes sees one external memory provider: `brainstack`.
2. Built-in Hermes memory and built-in user profile are fully displaced.
3. `profile`, `continuity`, `graph_truth`, and `corpus` have separate ownership.
4. Token savings is a first-class success axis, not a late optimization pass.
5. Temporal change must preserve prior states instead of destructive overwrite.
6. Conflicts should be surfaced rather than silently flattened away.
7. Provenance should be visible by default, but not spammy.
8. The system should be highly automatic with low manual maintenance.

## Role Map

- `Hindsight`
  - owns recency, continuity, and session learning

- `Graphiti`
  - owns canonical entities, relations, temporal truth, and supersession

- `MemPalace`
  - owns corpus/document memory and section-aware packing

- `Mira-inspired control plane`
  - owns working-memory orchestration, packing pressure, confidence-aware explanation depth, and tool avoidance policy

- `RTK`
  - early sidecar for token/output discipline

- `My-Brain-Is-Full-Crew`
  - early workflow shell, not first-wave top-level orchestrator

## Execution Rules

### Rule 1. Freeze ownership before deep integration
Do not let two layers own the same memory view.

### Rule 2. Do substrate before orchestration
Do not make complex orchestration choices before continuity, graph truth, and corpus paths exist.

### Rule 3. Do displacement after control is real
Do not fully displace native Hermes behavior until the composite path is coherent enough to carry live traffic.

### Rule 4. Add sidecars only after boundaries exist
RTK and workflow-shell integration are early, but they still come after memory boundaries are defined.

### Rule 5. Treat acceptance axes as release gates
Passing one axis does not excuse failure on the others.

### Rule 6. Re-evaluate after every phase
The roadmap is not a blind commitment. After each phase:

- check whether the phase exit gate truly passed
- check whether the next phase still makes sense
- allow redesign, merge, split, or reorder if the new reality justifies it
- record the recommended next step and recommended agent effort

### Rule 7. Do not depend on broken orchestration
In the current Codex CLI environment, subagent-driven GSD orchestration is unreliable and can stall. Until that runtime issue is fixed:

- do not make progress contingent on subagent completion
- do not route mandatory phase work through subagent-only paths
- prefer single-agent execution that still preserves GSD artifacts and gates

## Phase Order

1. Phase 1: foundation
2. Phase 2: continuity
3. Phase 3: graph truth
4. Phase 4: corpus
5. Phase 5: control plane
6. Phase 6: native displacement
7. Phase 7: RTK sidecar
8. Phase 8: My-Brain-Is-Full-Crew workflow shell

## Immediate Next GSD Step

Execute Phase 1 in single-agent mode to lock:

- provider contract
- memory-view ownership
- sidecar and shell boundaries
- minimum Hermes patch scope

Only after that should implementation of the substrate phases begin.

## Agent Effort Scale

- `medium`
  - bounded implementation or integration work with low ambiguity

- `high`
  - substantial architecture or integration work with moderate ambiguity

- `veryhigh`
  - highly coupled or high-risk work where a wrong move would ripple across the stack
