# Phase 56 Implementation Contract

## invariant

The system is not inspector-ready until the deployed installed runtime is canonical, explicit native rule packs no longer become Brainstack behavior authority, internal runtime status text cannot contaminate transcript memory, and the corrected state can be reproduced from the `Brainstack-phase50` source-of-truth repo by install/wizard flow.

This contract does not treat the remaining defect as merely “dirty state.”
It includes active authority residue and proof-surface gaps.

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

- all source fixes live in `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`
- `finafina` is repaired only through source-copy/install/wizard reproduction and runtime-only local config
- deployed native explicit profile state is canonical:
  - reusable naming truth is stored canonically
  - explicit packs are not flattened into degraded bundled prose when the contract expects canonical explicit entries
- explicit native rule packs do not produce active Brainstack behavior authority:
  - no active `behavior_contracts` for those packs
  - no active `compiled_behavior_policies` for those packs
  - no ordinary-turn policy projection from those packs
- bounded mirror/archive artifacts may remain only if they are clearly non-authoritative
- internal runtime status strings are excluded from transcript persistence
- a fresh Hermes checkout can be brought into the corrected state from the source-of-truth repo by wizard/install
- installed runtime / provider-path proof is green
- real Discord UI proof is green on the installed runtime

## prohibited outcomes

- fixing only `finafina` while leaving `Brainstack-phase50` unable to reproduce the state
- keeping active `behavior_contract` or `compiled_behavior_policy` artifacts for native explicit rule packs and claiming they are harmless because config toggles are off
- preserving transcript contamination while hiding it only from the user-facing UI
- inventing new behavior or style-governor logic to replace the removed residue
- introducing migration logic that is specific to the current user, language, or current 21-rule example
- proving only on fresh temp homes while deployed long-lived state remains non-canonical
- treating the phase as pure cleanup while active authority residue still survives

## proof expectation

The phase is not complete unless all of these are proven:

- the corrected behavior can be installed from `Brainstack-phase50` into a fresh Hermes checkout
- the installed runtime in `finafina` matches the source-of-truth fix
- deployed `USER.md` / user-profile index state is canonical
- the live Brainstack DB contains no active explicit-rule-pack `behavior_contracts`
- the live Brainstack DB contains no active explicit-rule-pack `compiled_behavior_policies`
- transcript memory excludes internal runtime status strings
- installed runtime / provider-path proof is run on the installed runtime
- real Discord UI proof is run on the installed runtime
- no final proof is run on an unreproducible hand-patched state

## output required

- one narrow source-of-truth implementation
- one install/wizard proof on a fresh Hermes checkout
- one deployed-state canonicalization artifact
- one DB proof artifact for behavior-authority absence
- one transcript-hygiene proof artifact
- one final installed-runtime Discord verification note

## anti-goals

- no second implementation in `finafina`
- no heuristics, regex farms, locale parsers, or user-specific rescue logic
- no “good enough because the fresh harness is green”
- no leaving half-wired behavior-authority code paths active in storage, repair, or compiled-policy lanes
- no immediate return to feature work if the same inspector-blocking runtime path still carries critical/high debt
