# Phase 21 Behavior Bridge Truth

## Verified behavior truth

- Brainstack persisted the user-specific communication facts and preferences
- live behavior still drifted after reset:
  - emoji usage returned
  - overly generic AI tone returned
  - Bestie naming was not treated as the strong identity preference
  - formatting rules were not applied reliably

## Verified contract-path truth

- Brainstack already builds an active communication contract block
- that contract is injected into the system prompt through the memory manager
- however, the active contract path is narrower than the observed live rule set
- strict rerun audit showed that profile/contract durability is the authoritative success path on this axis:
  - `current_state_pairs = []`
  - `has_expected_current_states = false`
  - but the persisted profile rows, injected contract, and live post-reset behavior still aligned on the target rules
- therefore empty graph current-state representation was audited as a non-blocking representation difference for Phase 21, not as a contract-owner failure

## Deeper seam identified

Two concrete bridge failures were verified:

1. contract key-space fragmentation
- Tier-2 slot normalization and profile stable-key construction can produce duplicated keys like:
  - `preference:preference:communication_style`
- contract extraction expects:
  - `preference:communication_style`
- result:
  - the rule is remembered but does not enter the active contract path correctly

2. contract selection too narrow
- current active contract selection only captures a small subset of communication rules
- important live rules from the manual audit are not reliably promoted into the contract:
  - Humanizer-style variants
  - message structure / new-line preference
  - pronoun capitalization preference
  - AI naming preference
  - language preference variants

## Repair decision

- fix contract-key canonicalization at the shared profile key seam
- broaden contract promotion to the real communication-rule class
- do not add a second persona channel
- only strengthen prompt wording if the same contract path remains the owner
- treat profile/contract durability plus behavior proof as the acceptance authority on this axis; do not force a second representation channel just to make the graph view look symmetrical
