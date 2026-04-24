# Phase 40 Implementation Contract

## invariant

Brainstack must not let canonical memory authority drift across read, write, repair, and debug surfaces.

## required implementation properties

- nominal read surfaces do not mutate durable truth
- explicit write paths are auditable and typed by operation
- historical polluted generations can be repaired without hiding the repair
- a canonical style generation suppresses style-authority regeneration from transcript/profile fallback
- exact canonical recall and ordinary-turn active lane share one authority lineage
- compiled policy self-heals from clean canonical truth or reports explicit fail-closed absence
- debug truth is machine-readable and out-of-band
- operator debug output clearly separates:
  - Brainstack-owned surfaces
  - host/runtime non-Brainstack layers

## prohibited outcomes

- read-only query paths that still create, patch, or supersede durable truth
- profile or graph residue acting as an implicit replacement contract authority
- separate drifting truths for:
  - canonical contract
  - compiled policy
  - ordinary-turn active lane
- packet-facing write receipts or debug traces leaking back into the model-facing memory block
- wipe-as-solution being treated as the permanent fix
- new cue farms, language tables, or hidden heuristic routing as part of this phase

## likely implementation seams

- `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/__init__.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/db.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/retrieval.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/profile_contract.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/operating_truth.py`

## verify contract

- clean-store replay:
  - explicit contract teaching survives reset
  - exact recall and active lane expose the same authority lineage
- dirty-store replay:
  - polluted historical state is repaired audibly
  - style residue no longer regenerates active authority
- transaction proof:
  - read-side effect count is zero for nominal recall/debug queries
- convergence proof:
  - compiled policy source lineage matches active canonical lineage
  - active lane source lineage matches active canonical lineage
- operator proof:
  - out-of-band debug snapshot exists
  - packet-facing debug contamination is absent

## canonical principle reference

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`

## recommended model level

- `xhigh`
