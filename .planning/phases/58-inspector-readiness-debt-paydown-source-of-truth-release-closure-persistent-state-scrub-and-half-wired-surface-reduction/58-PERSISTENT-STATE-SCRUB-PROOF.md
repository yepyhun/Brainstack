# Phase 58 Persistent-State Scrub Proof

## Before

Observed on the installed `finafina` runtime before the Phase 58 scrub:

- `transcript_entries` contained one internal assistant residue row:
  - `Assistant: Operation interrupted: waiting for model response (2.7s elapsed).`
- `behavior_contracts` contained one style-contract residue row:
  - `stable_key = preference:style_contract`
  - `status = superseded`
  - `source = tier2_llm`
- `compiled_behavior_policies = 0`

## Source-of-truth mechanism

The cleanup is now source-of-truth authored in:

- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/db.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/scripts/install_into_hermes.py`

The two new store-level cleanup paths are:

- `scrub_transcript_hygiene_residue()`
- `purge_style_contract_behavior_residue()`

The installer invokes those paths through runtime DB canonicalization, so the proof is reproducible on install.

## After

Observed on the installed `finafina` runtime after reinstall and rebuild:

- `interrupt_transcript_hits = 0`
- `style_contract_behavior_rows = 0`
- `active_behavior_contracts = 0`
- `superseded_behavior_contracts = 0`
- `compiled_behavior_policies = 0`
- `style_contract_profile_items = 1`

## Interpretation

- the stale interrupt/status transcript contamination is gone
- the stale style-contract behavior row is gone
- the explicit rule pack remains only in the non-authoritative profile/archive lane
- the runtime no longer tells one story in `USER.md` and a contradictory one in `behavior_contracts`
