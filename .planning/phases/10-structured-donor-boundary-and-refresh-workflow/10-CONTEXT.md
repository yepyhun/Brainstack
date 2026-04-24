# Phase 10 Context

## Goal
Make the current Brainstack stack materially more modular and update-friendly without pretending that we already have a full one-click donor auto-update system.

## Why This Phase Exists
- The user explicitly wanted a modular, update-safe architecture from the start.
- The current implementation direction stabilized ownership and runtime behavior, but donor-inspired logic is still too baked into local Brainstack code.
- That creates a real maintenance problem:
  - upstream donor improvements are harder to adopt cleanly
  - donor-derived logic is not physically separated enough from Brainstack-owned logic
  - update claims can drift ahead of reality
  - half-wired refreshes become more likely because boundaries are implicit instead of contractual
- A full externalized one-click donor update system is possible later, but it is heavier than needed for the next practical step.

## Phase Boundary
- This phase is a middle path.
- It must not attempt full automatic donor replacement.
- It must create a structured donor boundary and refresh workflow that is honest, modular, and much easier to evolve later.

## In-Scope Donor Targets
- `Hindsight` style continuity/recency substrate
- `Graphiti` style graph/temporal truth substrate
- `MemPalace` style corpus/document substrate

## Required Standard
- No fake modularity.
- No donor code hidden inside unrelated Brainstack files without an explicit boundary.
- No new half-wired paths where a boundary exists in code but the host still uses the old path.
- No marketing claim of “one-click updates” unless the refresh workflow truly does that.

## Required Outputs
- a donor boundary matrix
- a donor manifest / registry artifact
- explicit adapter seams for in-scope donor-backed layers
- a bounded refresh workflow document or script entrypoint
- compatibility and anti-half-wire tests proving the host still uses the intended Brainstack path

## Anti-Half-Wire Guardrails
- Every new boundary must be checked in three ways:
  - code location: donor-facing code is isolated in obvious modules
  - runtime path: Hermes still calls the intended Brainstack seam
  - regression proof: tests fail if the old or wrong path silently remains active
- Silent fallbacks and dual-path behavior count as failure, not as graceful compatibility.
- “Looks modular” is not enough; the refresh flow must show what changed, what is pinned, and what still requires manual judgment.

## How Graph MCP Should Be Used
- Use `code-review-graph` with full postprocess when stable enough to validate:
  - caller/callee path after refactors
  - moved file ownership
  - whether old codepaths still remain live
- Treat graph output as support evidence only.
- Final Phase 10 verdicts must still be backed by code references and executable tests.

## Canonical References
- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`
- `.planning/phases/01-brainstack-composite-provider-foundation/01-IMPLEMENTATION-CONTRACT.md`
- `.planning/phases/06.1.1-ai-wiring-audit-and-anti-goal-drift-gate/06.1.1-CONTEXT.md`
- `.planning/phases/06.2-pragmatic-real-world-e2e-memory-proving/06.2-01-SUMMARY.md`
- `.planning/phases/09-hindsight-lossless-transcript-hardening/09-SECURITY.md`

## Non-Goals
- Do not turn donor projects into live parallel runtimes inside Hermes.
- Do not build full automatic upstream merge/update machinery in this phase.
- Do not regress the single Brainstack ownership model.
- Do not add benchmark-shaped shortcuts or fake adapter layers that only rename the same baked-in code.

## Output Expectation
This phase should leave behind an honest, maintainable middle-ground architecture:
- substantially more modular than the current baked-in donor state
- substantially easier to refresh safely
- still simple enough to implement without a massive replatforming step
