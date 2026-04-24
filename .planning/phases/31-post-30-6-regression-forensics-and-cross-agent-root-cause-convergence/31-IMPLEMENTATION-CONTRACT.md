# Phase 31 Implementation Contract

## invariant

Phase `31` must end with one accepted root-cause model that explains the live regression through concrete runtime evidence. No code patch belongs here.

## required implementation properties

- every conclusion must point to at least one of:
  - session trace evidence
  - live DB evidence
  - concrete source/runtime code seam
- the final writeup must explicitly classify:
  - primary causes
  - supporting symptoms
  - non-causes
- the writeup must state whether the active canonical contract is:
  - complete
  - partial
  - partial and authoritative
  - superseded incorrectly
- the writeup must state whether Brainstack-only tool blocking is:
  - uniform
  - sequential-only
  - concurrent-only
  - half-wired

## prohibited outcomes

- no patch disguised as “forensics”
- no explanation that relies on private intuition about model behavior
- no “likely” conclusion without a corresponding code or runtime seam

## likely implementation seams

- [__init__.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/__init__.py)
- [db.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/db.py)
- [style_contract.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/style_contract.py)
- [run_agent.py](/home/lauratom/Asztal/ai/hermes-final/run_agent.py)
- [brainstack_mode.py](/home/lauratom/Asztal/ai/hermes-final/agent/brainstack_mode.py)
- live session traces under:
  - `/home/lauratom/Asztal/ai/hermes-final/hermes-config/bestie/sessions/`

## verify contract

Verification is complete when:

- the root-cause reading can explain the pasted Discord log without hand-waving
- the accepted reading narrows the hotfix surface to a small, concrete set of seams

## canonical principle reference

- [IMMUTABLE-PRINCIPLES.md](../../IMMUTABLE-PRINCIPLES.md)

## recommended model level

- `xhigh`
