# Phase 21 Context

## Why this phase exists

The manual deployed-live conversation audit exposed a different class of problem than the earlier graph/runtime phases.

The main issue is no longer:

- graph availability
- native aggregate availability
- reset/finalize lifecycle loss

The new issue is:

- Brainstack captures personal facts and style rules reasonably well
- but those rules do not reliably become behavior
- and the assistant can still improvise false system explanations or manual file/tool detours around Brainstack-only memory ownership

This makes the current product state dangerous in a specific way:

- memory capture looks healthier than memory-governed behavior
- style and identity can be remembered but not obeyed
- speculative assistant self-explanations can get promoted into durable memory

## What the manual audit established

### Stronger than expected

- passive Brainstack capture persisted:
  - Tomi identity
  - Hungarian preference
  - Humanizer-style preference
  - Bestie naming
  - Laura cat injury
  - formatting preferences
  - the rule to stop using manual tools for memory storage

### Weaker than required

- reset-boundary behavior still drifted back to default AI style
- the assistant made unsupported claims about:
  - `persona.md`
  - Humanizer file loading
  - passive startup injection
  - per-message persona delivery
- a manual `write_file` / `execute_code` path was used for memory-like behavior even though Brainstack-only ownership should have prevented that
- some of those speculative claims were themselves promoted into durable memory records

### Important architectural correction

The project doctrine and runtime config already point to Brainstack-only ownership on the personal-memory axis:

- `memory.provider: brainstack`
- `memory.memory_enabled: false`
- `memory.user_profile_enabled: false`

So this phase is not about “making persona.md stronger”.

It is about:

- restoring Brainstack-only ownership cleanly
- making Brainstack’s active communication contract reliably affect live behavior
- preventing assistant speculation from contaminating durable memory
- preserving useful native host capabilities where they do not become competing personal-memory owners

## Why this phase must not be a band-aid

The tempting shallow reaction would be:

- tweak a persona prompt
- add another style warning
- patch one tool call
- patch one transcript pattern

That would be the wrong response.

The audit indicates a deeper shared seam:

- ownership boundaries between Brainstack and host/file/skill/tool paths
- prompt-layer precedence between Brainstack contract and host identity/context files
- ingest hygiene between user facts and assistant self-narrated internals

So the phase must explicitly check:

1. is the visible bug only the surface symptom?
2. is there a deeper shared layer causing the same class elsewhere?
3. are there adjacent similar failures from the same ownership / prompt / hygiene architecture?

## Current likely seam map

The manual audit already narrowed the likely shared seams. Phase 21 should not rediscover them from zero; it should verify and then repair the correct layer.

### Ownership seam candidates

- host integration policy / Brainstack-only mode gating
- tool-selection or fallback logic that still permits personal-memory detours
- context-file / host-persona loading paths that can be mistaken for the owner of personal style or identity memory

### Behavior seam candidates

- Brainstack contract/profile block construction
- prompt assembly and placement relative to host system prompt content
- precedence or salience problems where remembered communication rules are present but not behavior-dominant

### Hygiene seam candidates

- ingest normalization that cannot distinguish:
  - user preference
  - assistant commitment
  - assistant speculation
  - tool narration
- reconciliation rules that over-promote confident assistant text into durable truth
- temporal normalization rules that accept conflicting partial-date interpretations without enough conflict handling

## Concrete planning doctrine for this phase

Phase 21 should behave like a root-cause isolation and shared-seam repair phase, not a prompt-tuning sprint.

That means:

- prove which seam is active before writing the fix
- decide the narrowest shared layer that explains the whole failure class
- check sibling failures before finalizing the patch
- keep repair bounded, but make it class-complete for the verified seam
- prefer one architecture-led fix plus proof over several local exceptions

## Target architecture after Phase 21

After this phase, the system should have one clear doctrine on this axis:

- Brainstack owns personal identity, personal style, and personal preference memory
- host persona/context files may exist as compatibility shell inputs, but they are not allowed to become the hidden mutable source of user-specific truth
- native host capabilities like scheduling or automation may remain in place for their own domain, but they must not become a second persistence/retrieval channel for personal-memory truth
- assistant live behavior should be governed by the same remembered contract that is stored and injected, not by ad hoc fallback improvisation
- durable memory should represent grounded user truth and justified system state, not confident assistant mythology about internals

This is the important large-picture point:

- the phase is not only fixing tone drift
- it is restoring a single coherent ownership model for personal memory and behavior shaping

## End-state invariants

Phase 21 should leave behind stable invariants, not just one green rerun.

1. Single-owner invariant.
   - personal memory has one authoritative owner in Brainstack-only mode
   - any residual host role is explicit compatibility shell, not shadow ownership
   - general native host features may remain, but they cannot act as a second owner on this axis

2. Capture-to-behavior invariant.
   - if a style/identity rule is captured and injected, it must have a reliable path to live behavior after reset

3. No-fantasy-memory invariant.
   - assistant speculation about system internals must not be able to crystallize into durable truth through the normal ingest path

4. Honest-boundary invariant.
   - if a host dependency remains, it is named and bounded instead of denied or hidden behind misleading self-explanations

5. Representation-boundary invariant.
   - profile/contract durability is the authoritative success criterion on this axis
   - graph current-state representation is desirable, but Phase 21 does not fail solely because communication rules are represented there less directly as long as profile, injection, and behavior stay aligned

## What this phase is not

- not a persona.md strengthening phase
- not a prompt-only patch phase
- not a benchmark phase
- not a large host rewrite
- not a SOUL-removal crusade without proof
- not a reactive one-bug patch train

## Honest target

Produce a donor-first, architecture-level repair plan and implementation path for:

- Brainstack-only personal-memory ownership
- communication-contract-to-behavior enforcement
- durable-memory hygiene against assistant speculation

while proving the deeper layer and adjacent similar failure classes were actually checked, not assumed away.
