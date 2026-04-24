# Phase 63 Implementation Contract

## execution intent

Design the Brainstack hot path so ordinary task/operating behavior becomes locally decidable from typed Brainstack-owned substrates, while remote `structured_understanding` is demoted out of mandatory authority.

## required architecture discipline

### 1. local typed understanding is not heuristic revival

- execution must not introduce cue tables, locale dictionaries, phrase farms, or pattern lists that merely rename the old heuristic layer
- "deterministic" is acceptable only when it is driven by typed substrates and explicit schema, not wording matches

### 2. hot-path authority must become local

- ordinary task/operating reads and ordinary task/operating capture decisions must no longer require successful remote semantic classification
- failure of the remote seam must not leave the ordinary kernel unable to decide its safe behavior

### 3. use existing typed Brainstack structures first

- existing candidates include:
  - operating records
  - task memory
  - operating context
  - transcript structure
  - provenance
  - timestamps
  - live-system-state rows
- execution must justify any new substrate or new record family

### 4. read and write authority may differ, but the substrate should stay shared

- read-path routing and write/capture eligibility do not have to be the same function
- they should still derive from one coherent typed substrate model
- execution must avoid parallel local rule systems for read vs write

### 5. ambiguity must degrade safely

- if the local typed substrate cannot prove task/operating classification strongly enough, the kernel must degrade to:
  - fact-safe read behavior
  - no-capture write behavior
- the phase must not replace remote failure with local over-capture or false specificity

### 6. multimodal-first discipline

- any proposed hot-path architecture must remain valid for future turn envelopes that include attachments, tool outputs, or non-text event structure
- a design that only works by tokenizing natural-language text is not acceptable as the new base architecture

### 7. host seam rule

- no new host seam should be added unless execution proves the required typed substrate cannot be obtained inside current Brainstack ownership
- if a minimal host seam is requested later, the phase must name the exact missing typed field and why Brainstack cannot otherwise derive it

### 8. migration rule

- execution must define an explicit cutover map from current remote-understanding call sites to new local typed understanding
- half-wired coexistence is not acceptable as a final state

### 9. closeout truth rule

- closeout must say clearly:
  - which ordinary decisions are now locally decided
  - which LLM-based decisions, if any, remain
  - why those remaining decisions are no longer hot-path authority

## required design decisions to freeze before execution

- exact definition of the local typed substrate
- exact separation between:
  - read-path route determination
  - write/capture eligibility
  - off-path enrichment/consolidation
- exact degraded behavior when local proof is insufficient
- exact migration/cutover boundary for existing remote-understanding call sites
- exact multimodal compatibility story for the chosen substrate

## accepted change shapes

- local typed record or normalized-turn architecture work inside Brainstack
- replacement of mandatory remote-understanding call sites in ordinary Brainstack paths
- tighter projection/use of existing authoritative records
- bounded off-path demotion of remote understanding
- proof-oriented tests that verify no-heuristic compliance and hot-path availability

## rejected change shapes

- restoring old cue tables or phrase detectors
- replacing one remote understanding seam with another mandatory remote seam
- provider-specific tuning presented as the architectural fix
- host/runtime hidden classifier layers
- broad transcript dumping as a substitute for understanding
- one-user or one-language special-case routing

## proof obligations for the later execute step

- show the exact ordinary call sites that no longer depend on remote `structured_understanding`
- show that ordinary task/operating behavior still degrades safely without remote success
- show that the new architecture is not text-only by design
- show that no heuristic cue farm was reintroduced
- show that current Phase `62` live-state authority remains cleanly separated from the new hot-path logic

## inspector note

This phase is explicitly where the project proves it can move from "remote semantic classification with containment" to "local typed kernel authority" without regressing into heuristics. Anything that merely hides the old dependency or smuggles back cue-driven routing fails the purpose of the phase.
