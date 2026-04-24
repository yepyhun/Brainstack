# Phase 52 Implementation Contract

## invariant

Explicit user/profile truth must be anchored to the Hermes native explicit-memory seam. Brainstack may mirror, reconcile, and augment that truth, but it must not remain a parallel first-class profile governor over ordinary product behavior.

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

- the Hermes native explicit-memory seam is treated as the first explicit user-profile surface
- built-in memory writes remain the canonical write path for explicit user/profile facts
- Brainstack mirrors native writes through the provider seam instead of replacing them
- the mirror contract is one-way and idempotent:
  - mirror records carry native write identity and source generation
  - mirrored native truth never bounces back upstream as a fresh explicit host write
  - reapplying the same native write converges rather than duplicating truth
- an explicit precedence table exists for every truth class and leaves no dual-primary ambiguity
- Brainstack retains kernel roles:
  - continuity
  - transcript
  - task truth
  - operating truth
  - graph / corpus
  - cross-store consistency
- Brainstack custom profile/style files are demoted where they currently imply first-class profile primacy
- ordinary chat is not re-captured by Brainstack style or behavior governance
- the plan must be file-level, not only conceptual
- the plan must include migration semantics for already-existing Brainstack-held explicit profile/style state
- the plan must include an anti-regression rule that prevents Brainstack inferred or extracted profile candidates from silently re-becoming first-class explicit truth
- the anti-regression rule must explicitly cover:
  - transcript-derived style atom creation in `profile_contract.py`
  - profile+graph contract rebuild in `retrieval.py`
  - ordinary-turn query-shape escalation in `control_plane.py`
- the phase must align shipped parity surfaces:
  - README
  - installer
  - doctor
  - host payload
  - tests
  - proof/docs
- the phase must define native-unavailable semantics that fail explicitly instead of residue reconstruction

## prohibited outcomes

- a second explicit profile authority path that competes with the native explicit-memory seam
- keeping Brainstack profile-governance logic simply because it already exists
- gutting useful Brainstack kernel intelligence in the name of simplification
- introducing more host-level rule pressure while trying to simplify
- vague “we should probably trim this” wording without file ownership and execution order
- allowing candidate or extracted Brainstack profile state to bypass native explicit profile authority
- allowing mirrored native truth to re-enter the host as a new explicit write and create mirror loops
- using transcript/profile residue as an implicit replacement when native explicit authority is unavailable

## required output

The phase must produce one explicit file-level decision matrix with four buckets:
- keep
- demote
- remove or sharply reduce
- re-anchor / rebuild

It must also define:
- the authority precedence matrix
- the one-way idempotent mirror contract
- the migration/re-anchor contract
- the native-unavailable contract
- the tooling/docs/payload parity checklist
- the execution order for those buckets

## proof expectation

Later execution must be able to prove all of these:
- native explicit profile write works
- Brainstack mirror works
- ordinary chat remains natural
- explicit recall still works
- post-reset memory behavior remains coherent
- no shadow explicit profile authority reappears in Brainstack-only paths
- no mirror loop or duplicate-native-write truth appears
- README / installer / doctor / host payload / tests describe and verify the same architecture

## recommended model level

`xhigh`
