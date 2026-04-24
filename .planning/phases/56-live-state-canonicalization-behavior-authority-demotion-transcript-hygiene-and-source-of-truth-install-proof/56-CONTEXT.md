# Phase 56 Context

## why this phase exists

The inspector-blocking defects are no longer hypothetical. They were observed in the live installed `finafina` runtime after real Discord use.

The main findings that trigger this phase are:

- deployed `USER.md` is still degraded and non-canonical
- active `behavior_contracts` and `compiled_behavior_policies` still exist for the explicit native rule pack
- internal runtime status text entered transcript memory as assistant content
- fresh-state proof from earlier phases does not guarantee that the long-lived installed runtime is clean

## verified live-state evidence

Observed on the installed `finafina` runtime:

- `/home/lauratom/Asztal/ai/finafina/hermes-config/bestie/memories/USER.md`
  - contains degraded bundled entries like:
    - `User's Discord name is LauraTom but should be addressed as Tomi`
    - `Communication rules: 1. ... 21. ...`
    - `Address user as Tomi, not LauraTom`
  - does not contain canonical `Preferred user name:` or `Assistant name:` lines
- `/home/lauratom/Asztal/ai/finafina/hermes-config/bestie/brainstack/brainstack.db`
  - contains active `behavior_contracts`
  - contains active `compiled_behavior_policies`
  - contains `native_profile_mirror` plus tier2-derived identity/shared-work rows from the same live conversation
- `transcript_entries`
  - contains assistant content such as:
    - `Operation interrupted: waiting for model response (...)`

These findings mean the product is not yet inspector-ready even if earlier fresh-state proof artifacts were green.
The problem is not only dirty deployed state; it is also still-active authority residue.

## accepted diagnosis

The remaining defect family is:

1. source-of-truth and installed-runtime divergence
2. explicit native rule packs still escalating into Brainstack behavior-authority artifacts
3. internal runtime/status surfaces contaminating transcript memory
4. deployment proof not yet anchored to the `Brainstack-phase50` wizard/install path

The remaining defect family is not:

- a need for more capability work
- a need for stronger memory intelligence
- a need for a new guardrail layer

This is not a request for:

- more memory intelligence
- a stronger style governor
- more prompt pressure
- locale-specific extraction

It is a request for:

- canonical storage repair
- authority-lane cleanup
- transcript hygiene
- source-of-truth install discipline

## source-of-truth rule for this phase

- edit code in:
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`
- deploy/test into:
  - `/home/lauratom/Asztal/ai/finafina`
- do not treat `finafina` as a second codebase

## proof stratification

This phase treats two proof surfaces separately:

1. installed runtime / provider-path proof
   - confirms the corrected source surfaces install and run coherently
2. real Discord UI proof
   - confirms the actual user-facing product surface behaves correctly

Neither proof surface substitutes for the other.

## design guardrails

- native Hermes explicit user/profile truth remains primary
- Brainstack remains memory substrate / mirror / retrieval kernel
- explicit rule packs may remain as native truth plus bounded archive/mirror
- explicit rule packs must not remain active behavior authority
- transcript memory must only contain legitimate user/assistant conversational content, not internal runtime status

## anti-drift reminders

- do not solve canonicalization with one-off data hacks that the wizard cannot reproduce
- do not accept “disabled config flags” as proof that behavior-authority residue is harmless if the DB/storage/repair path is still active
- do not accept a fix that works only on fresh temp homes
- do not solve the current example with user-specific or language-specific handling
- do not resume feature-building immediately after this phase if critical/high debt remains open on the same runtime path
