# Project

## Name
Hermes Brainstack

## Goal
Build a modular, update-safe second-brain memory system for Hermes Agent that:

- preserves cross-session continuity
- models durable facts, relations, and temporal change
- handles large document corpora such as books, textbooks, and notes
- noticeably improves agent intelligence and continuity
- reduces token usage aggressively through selective recall and context packing

## Host
Latest `hermes-agent` clone at:

- `/home/lauratom/Asztal/ai/veglegeshermes-source`

Brainstack source and GSD planning live at:

- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`

## Primary Direction
Do not continue the old `hermes-agent-core2` kernel line.

Use Hermes latest as the host runtime and implement one external composite memory provider:

- `brainstack`

Hermes should see exactly one external memory provider.

Behind that provider, use real modular sublayers:

- `Hindsight` for recency, continuity, and turn/session learning
- `Graphiti` for canonical entity-relation-temporal truth
- `MemPalace` for large corpus storage and document/context packing

Add a control plane inspired by `mira-OSS`, but do not treat Mira as a fourth memory layer.

## Key Architectural Decision
Functionally replace native memory behavior without hard-forking Hermes core.

That means:

- disable built-in prompt memory (`memory_enabled: false`, `user_profile_enabled: false`)
- keep Hermes host contract intact
- provide one composite external provider
- if needed, apply only a small compatibility patch to remove the built-in `memory` tool from the live tool surface

## Non-Goals
- Do not create another benchmark-first kernel
- Do not bake English benchmark heuristics into the live memory path
- Do not run multiple peer external memory providers inside Hermes
- Do not make `NeuronFS`, `RTK`, or `My-Brain-Is-Full-Crew` into competing core memory layers

## Desired Memory Views
The target system should expose four stable memory views:

1. `profile`
   Stable user identity, preferences, habits, style, and long-lived rules.

2. `continuity`
   Recent work, active projects, recent session summaries, conversation continuity.

3. `graph_truth`
   Entities, relations, current/previous state, supersession, time-aware truth.

4. `corpus`
   Books, notes, domain documents, section-aware long-form knowledge.

## Extension Policy
The system must remain extensible, but new ideas must enter through bounded slots:

- donor capability
- sidecar service
- control-plane policy
- adapter enhancement

New ideas must not become new peer memory cores by default.

## Current State
After milestone `v2.0`, Hermes Brainstack now ships with:

- one Hermes-facing `brainstack` provider
- stable `profile`, `continuity`, `graph_truth`, and `corpus` shelves
- a bounded working-memory control plane
- displaced native Hermes memory behavior on the Brainstack path
- bounded RTK sidecar integration
- bounded My-Brain-Is-Full-Crew shell integration
- append-only transcript retention
- explicit donor boundary seams and a bounded donor refresh workflow

## Current Milestone: v2.1 Brainstack Profile Intelligence

**Goal:** Upgrade Brainstack profile memory from regex-first extraction to a layered extraction pipeline with safe implicit preference inference.

**Target features:**
- explicit profile extraction seam with bounded Tier-1 and Tier-2 slots
- Shiba-style Tier-2 implicit preference inference behind Brainstack ownership
- confidence-gated write policy with temporal supersession and correction safety
- stronger everyday preference recall without turning profile memory into a hallucination source

## Post-v2.0 Known Limits

- donor refresh is review-first, not one-click automatic
- implicit preference extraction is still regex-first rather than LLM-assisted
- requirements traceability should become more formal before the next milestone archive

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**
1. Requirements invalidated? → move them out or rewrite them explicitly
2. Requirements validated? → mark them with the milestone/phase that proved them
3. New requirements emerged? → add them to the active milestone scope only if they are truly in-scope
4. Decisions to log? → keep them explicit, especially around ownership and safety
5. \"What this is\" still accurate? → update it if reality drifts

**After each milestone:**
1. Full review of all sections
2. Core value check
3. Out-of-scope audit
4. Current-state and known-limits refresh

---
*Last updated: 2026-04-10 for v2.1 milestone definition*
