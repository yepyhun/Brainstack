# Phase 58 Hard Gates

## hard gate 1: source-of-truth discipline

All code changes for this phase are authored in:

- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`

and only then installed/proved on:

- `/home/lauratom/Asztal/ai/finafina`

No target-only fix counts.

## hard gate 2: clean releasable source repo

At phase close:

- `Brainstack-phase50` has no unexplained dirty worktree
- the source repo passes release hygiene checks
- the wizard/install fixes needed for the runtime are committed in the source repo, not left as local residue

## hard gate 3: persistent-state hygiene

On the installed runtime:

- interrupt/status transcript contamination rows are absent after the scrub/migration
- stale authority residue from native explicit rule packs is absent or clearly demoted into non-authoritative archival storage
- no `compiled_behavior_policies` remain for this defect family

## hard gate 4: half-wired surface reduction

For the major half-wired or dead-looking shipped surfaces reviewed in this phase:

- each one has an explicit decision:
  - remove
  - demote to bounded compatibility shim
  - keep with documented reason
- no obviously stale governor residue is left in shipped source by accident

## hard gate 5: installer and doctor proof

The source-of-truth installer and doctor must prove the corrected state on the target runtime, including:

- dependency guards such as `croniter`
- runtime wiring expectations
- source/runtime compatibility expectations

## hard gate 6: targeted validation

Targeted tests covering all touched debt families must pass.

This includes at least:

- persistent-state cleanup paths
- installer/doctor changes
- any compatibility-surface deletion/demotion paths
- any runtime behavior affected by the cleanup

## hard gate 7: planning debt closure

`ROADMAP.md`, `STATE.md`, and touched phase artifacts must no longer leave stale open-seeming critical/high debt wording unresolved.

If an older concern is still real, it must be explicitly carried forward.
If it is no longer real, it must be explicitly closed or marked historical.

## hard gate 8: inspector-proof coherence

The final story told by:

- the source repo
- the installed runtime
- the live persistent state
- the planning / execution artifacts

must be coherent.

No false closure is allowed where one surface says “clean” while another still visibly carries stale residue.

## hard gate 9: no false cleanup

The phase fails if it achieves cleanliness by:

- hiding rows instead of scrubbing/migrating them
- deleting code without validating runtime entry points
- rewriting planning text to sound clean while the runtime or repo is still dirty
- keeping new fixes local and unreleased in the source repo
