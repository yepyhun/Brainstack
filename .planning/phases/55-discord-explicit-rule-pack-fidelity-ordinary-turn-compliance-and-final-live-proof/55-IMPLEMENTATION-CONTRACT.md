# Phase 55 Implementation Contract

## invariant

The remaining product defect must be fixed by strengthening explicit rule-pack truth fidelity across capture, persistence, recall, and Discord delivery, not by reintroducing Brainstack governance, heuristic rule mining, or one-off obedience hacks.

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

- explicitly taught multi-rule packs must persist as first-class durable truth
- explicit rule-pack truth must remain owner-correct:
  - host-owned on the native explicit seam
  - mirrored or recalled by Brainstack without authority takeover
- rule-pack persistence must preserve:
  - count
  - boundaries
  - semantic meaning
- same-session and post-reset recall must return the full taught pack:
  - no omissions
  - no semantic inversions
  - no “I do not remember the rules” after successful teaching
- ordinary Discord replies after successful teaching must reflect the stored pack without:
  - warnings
  - internal explanations
  - repeated requests to resend the rules
- the Discord surface must not emit lifecycle, rate-limit, reset, token-usage, or model-switch noise during ordinary conversation
- the implementation must remain generic:
  - no language-specific contract
  - no current-user contract
  - no text-only schema assumption

## prohibited outcomes

- adding a new behavior governor, rule engine, or style-policy layer
- adding rule-slot taxonomies, field enums, or parser tables for the current proof case
- adding regex or keyword logic whose purpose is to recognize the current rule pack
- solving fidelity with prompt pressure alone while the stored truth remains weak
- solving Discord cleanliness by hiding symptoms while the underlying truth path remains wrong
- accepting a result where the bot can recite the pack but still drifts in ordinary turns
- accepting a result where ordinary turns improve only for the current Hungarian example

## proof expectation

The phase is not complete unless all of these are proven:

- explicit rule-pack teaching works on the running Discord product
- successful teaching produces durable truth that survives reset
- same-session recall returns the full taught rule pack
- post-reset recall returns the full taught rule pack
- ordinary Discord replies follow the stored rule pack without warning or leak
- no semantic inversion occurs in recalled rules
- no internal lifecycle/status text leaks into ordinary Discord chat
- the result is green on two consecutive fresh-state Discord runs

## output required

- one narrow file-level implementation on the true owner seams
- one explicit artifact for rule-pack write lineage
- one explicit artifact for rule-pack recall fidelity
- one explicit artifact for Discord leak-free ordinary-turn proof
- one final Discord live-proof note covering both fresh-state runs

