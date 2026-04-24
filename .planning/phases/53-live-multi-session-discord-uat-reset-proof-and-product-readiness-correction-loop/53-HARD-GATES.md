# Phase 53 Hard Gates

## purpose

This file turns the Phase 53 product-readiness bar into concrete hard gates.

It exists to prevent a soft interpretation of “green enough”.

## fresh-state baseline

Every repeated ladder run must use the same fresh mutable state contract.

Must wipe:
- session replay artifacts
- Brainstack mutable session/continuity state
- session-local transcript caches
- session-local graph/corpus indexes derived from mutable state
- Hermes gateway/session runtime state

Must not wipe unless the rung explicitly requires first-teach-from-nothing:
- durable native explicit profile truth under test
- static config and auth state

Failure example:
- two supposed `fresh-state` runs reset different layers, making the ledger incomparable

## 1. authority purity

The system is not ready unless native explicit profile writes remain native-owned and Brainstack mirrors them one-way.

Required evidence:
- code-level proof that native explicit writes carry:
  - `native_write_id`
  - `source_generation`
  - `mirrored_from`
- dedicated authority-precedence test
- dedicated native-write-no-bounce test
- live evidence that a native explicit write becomes:
  - native first-class truth
  - Brainstack mirror only

Explicit failure examples:
- Brainstack creates a first-class explicit profile record from the mirrored native write
- Brainstack bounces a mirrored native write back as its own explicit profile truth
- a transcript/profile residue path outranks native truth
- cue-first logic overrides owner-first routing while an authority owner is available
- the runtime assumes a narrow personal-field schema as the only valid form of native explicit profile truth
- locale-specific parsing logic becomes the de facto owner of profile semantics
- an explicitly taught rule pack can only be recalled if Brainstack secretly injected communication-policy prose into ordinary turns

Required exemplar coverage:
- `Mik a szabályaid?` / `Tudod a 29 szabályt?` -> explicit archival rule-pack authority when such a pack was explicitly taught
- `Hány éves vagyok?` -> native explicit profile identity truth
- `Hol lakik Móni?` -> stable graph/logistics truth when present
- `Mik a mai feladataim?` -> task-memory authority
- `Mondd el viccesen` -> native preference/style seam, not ordinary-turn Brainstack governance

## 2. deterministic truth-state

The system is not ready if a ladder rung is intermittent.

Required rule:
- every ladder rung must run at least `3x` on fresh mutable state
- the truth-state and recall outcome must converge identically
- wording variance alone is not a failure

Explicit failure examples:
- same taught fact is sometimes recalled and sometimes lost
- supersession sometimes converges and sometimes duplicates
- reset sometimes clears session-local clutter and sometimes leaks it into durable truth
- explicit rule-pack recall sometimes works only after style-governance residue leaked into the prompt path

## 3. inspectability

The shipped Brainstack plugin must remain auditable and responsibility-bounded.

Required evidence:
- dependency / responsibility map for shipped Brainstack modules
- explicit note of which modules are:
  - native host anchors
  - Brainstack kernel owners
  - bounded archival / recall helpers
- proof that leftover governance or compatibility code was removed or sharply reduced when it no longer belonged to the product shape

Explicit failure examples:
- giant entry points keep silently reacquiring unrelated responsibilities
- demoted governance code remains in the hot path without an explicit bounded role
- an auditor cannot tell which module owns explicit profile truth versus mirror logic
- ordinary-turn prompt construction still depends on hidden communication-policy sections or style-slot renderers

## 4. adversarial anti-fragility

The system must survive non-happy-path pressure, not only clean linear teaching.

Required coverage:
- contradiction burst
- unexpected reset in the middle of a conversation
- controlled dual-principal isolation check

Explicit failure examples:
- the bot mixes session-local chat clutter into durable profile truth
- profile truth and session continuity collapse into one surface after reset
- one principal’s facts bleed into another principal’s recall

## 5. latency and leak hygiene

The system is not ready if it feels slow or leaks internals.

Required evidence:
- per-rung latency ledger
- separated measurement when possible:
  - end-to-end reply time
  - Brainstack-added overhead
- dedicated no-tool-trace-leak proof
- curated forbidden leak-family proof covering core internal pipeline names and tool traces

Explicit failure examples:
- tool or pipeline names leak into user chat
- internal blocker or trace copy leaks into the reply
- latency regresses materially without being tracked and explained
- ordinary turns contain Brainstack-generated communication-policy prose instead of clean user-facing conversation

Leak-family minimum coverage:
- tool traces such as `session_search` or `flush_memories`
- internal pipeline identifiers such as `control_plane`, `profile_contract`, `style_contract`, `output_contract`, `executive_retrieval`
- internal backend names leaking without user request
- blocker/internal-trace language
- Brainstack-generated communication-policy section titles or policy-sentence scaffolding in ordinary user replies

Latency bookkeeping rule:
- Brainstack overhead and end-to-end latency must be recorded separately whenever possible
- Brainstack overhead regressions are architecture defects
- end-to-end latency regressions are product defects even when provider/network latency is a factor

## release gate

Phase 53 is only complete when:
- the full ladder passes
- the full ladder passes again on fresh mutable state
- each rung is stable across `3x` fresh-state repetitions at the truth-state level
- hard-gate evidence exists for all five areas above
- no known dead or half-wired shipped-path governance fallback remains unresolved
- the product-ready gate is met without extending the phase into proactive continuity or personality-polish scope
- ordinary-turn success no longer depends on style/profile mining or communication-policy projection
