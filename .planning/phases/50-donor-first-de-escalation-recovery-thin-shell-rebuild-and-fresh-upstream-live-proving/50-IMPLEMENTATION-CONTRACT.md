# Phase 50 Implementation Contract

## invariant

The final product must behave like a thin orchestration shell around donor memory layers, not like a host-level rule-governance system. Simplification and subtraction in this phase apply to host control, not to donor memory intelligence.

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

- fresh upstream Hermes is the baseline for design and execution
- native Hermes files only take thin, upstream-friendly wiring changes where possible
- ordinary chat is not blocked by host-level Brainstack rule machinery
- generic blocked-output fallback chat replies do not remain as a normal delivery path
- ordinary chat remains chat-first on the host path
- donor/provider seams are the primary place where memory behavior lives
- donor/provider seams remain the primary place where memory intelligence lives
- Brainstack remains a shell for:
  - orchestration
  - ownership boundaries
  - cross-store consistency
- proving uses a fresh runtime/profile baseline
- the late rolling live-test loop may only add bounded shell-level corrections

## prohibited outcomes

- continuing to harden the old drifted architecture with more local patches
- keeping host-level generic rule blocking because it “sort of works”
- allowing the shell to become a second behavior engine over donor layers
- accidentally gutting donor/provider intelligence in the name of simplification
- adding new features during simplification
- using benchmark-shaped or single-prompt wins as proof of recovery

## keep / move / remove rule

- keep donor/provider intelligence
- move misplaced reply-path intelligence behind provider or memory-manager seams
- remove host-level ordinary-chat control paths that make the shell act like a rule engine

## required verification artifact

Produce one recovery proof artifact that records:
- fresh-upstream baseline commit
- keep/remove/thin-wire classification
- fresh runtime/profile proving setup
- rolling live proof cases
- what was removed to recover product behavior
- what bounded corrections were still needed after simplification

## recommended model level

`xhigh`
