# Workspace Boundaries

This project now has two active working roots. The old `hermes-agent-latest`
checkout is obsolete and may contain leftover planning files only.

## 1. Brainstack and GSD source of truth
- Path:
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`
- Use this for:
  - Brainstack code
  - installer / doctor / update scripts
  - Brainstack tests
  - Brainstack README and repo-facing docs
  - roadmap
  - phase context / plan / summary / UAT docs
  - STATE and milestone records
- Do **not** treat any old `memory-repo-bakeoff/hermes-agent-latest`
  checkout as an active repo or planning source.

## 2. Latest Hermes source and test checkout
- Path:
  - `/home/lauratom/Asztal/ai/veglegeshermes-source`
- Use this for:
  - latest Hermes host source
  - Brainstack install target checks
  - Docker / Discord / gateway smoke tests
  - host-side verification
- Do **not** make source-of-truth Brainstack edits here unless the goal is a
  temporary host diagnosis that will immediately be carried back into the
  Brainstack source repo and installer.

## Operational rule
- Build Brainstack and keep GSD planning in `Brainstack-phase50`.
- Install into `veglegeshermes-source` through the installer, then verify there.

If a fix is applied in the Hermes host checkout first for diagnosis, the same
fix must be carried back into the Brainstack source repo and integration kit
before the phase is considered complete.
