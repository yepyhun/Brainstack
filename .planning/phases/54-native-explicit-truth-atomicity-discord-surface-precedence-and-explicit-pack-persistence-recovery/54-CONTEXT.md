# Phase 54 Context

## why this phase exists

Phase 53 proved something important and uncomfortable:

- the harness/live-provider path can be green
- while the real Discord surface still fails in first-contact product behavior

The remaining failure is not “Brainstack is still too weak.”
The remaining failure is not “the model needs stricter rules.”

The remaining failure is a host/native-truth boundary defect:

- explicit durable truth is still too loosely dependent on model best-effort writes
- transport identity and explicit addressing truth are not cleanly separated on the Discord surface
- explicit multi-rule teaching does not yet land as a first-class durable truth path strongly enough to survive product use without ambiguity

## what phases 50-53 already established

- Phase 50:
  - host-level Brainstack governance had to be de-escalated
  - ordinary chat must not depend on Brainstack rule blocking
- Phase 51:
  - Brainstack is only partially synergistic unless it stays in the provider/kernel role and remains inspectable
- Phase 52:
  - explicit user/profile truth must be re-anchored to the Hermes native explicit-memory seam
  - Brainstack must mirror and augment, not govern
- Phase 53:
  - product proof must happen on the real Discord surface
  - no heuristics, no new schemas, no new governor layers are acceptable recovery paths

Phase 54 exists because a narrower residual defect family remained after those truths were established.

## concrete live failure family

The live Discord path exposed:

- `PermissionError` on session temp writes after reset/rebuild
  - this was an ownership/runtime bug and is now closed
- explicit addressing truth present in durable/native memory but not strong enough on first greeting
  - the bot knew `Tomi`
  - but still used `LauraTom` on the surface
- explicit rule-pack recall failure in a live path where the pack had not actually landed as durable truth
  - the system answered from the current stored state
  - but the product shape still made it too easy for explicit multi-rule teaching not to persist strongly enough

## root-cause reading

The deep issue is:

- too much of the explicit durable-truth path is still left to model interpretation and best-effort tool usage

The correct correction is not:

- stronger behavior rules
- stronger Brainstack governance
- new profile schemas
- locale-specific parser logic

The correct correction is:

- stronger explicit truth ownership
- stronger atomic write semantics
- stronger distinction between transport metadata and durable user truth

## target architecture reading

This phase should leave the system in a shape where:

- Hermes owns explicit truth capture on the native seam
- Brainstack mirrors that truth one-way and remains a memory kernel
- Discord platform metadata stays metadata
- user-facing addressing truth comes from explicit durable truth when present
- explicit multi-rule packs can be stored as first-class truth without free-chat mining or a narrow schema

## anti-regression reading

This phase must not regress into the exact trap that phases 50-53 were trying to escape.

Forbidden relapse patterns:

- “We need more rules so the model obeys better”
- “We need a canonical set of profile fields and validators”
- “We should infer the right durable truth from free chat with better regexes”
- “We should let Brainstack project more communication policy into ordinary turns”

Those are all wrong directions here.

## success reading

Success is not:

- the bot sounding more obedient
- the bot sounding more polished
- a single green harness run

Success is:

- explicit truth lands fully and durably
- the Discord surface uses the right truth owner
- Brainstack stays in the mirror/kernel role
- the fix remains generic, donor-first, and multimodal-safe
