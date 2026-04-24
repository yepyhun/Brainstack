# Phase 60 Implementation Contract

## top-level invariant

Phase 60 is only valid if it improves Brainstack's universal behavior rather than merely cleaning up one live Discord thread.

## ownership invariant

No change is allowed unless it can be stated in one of these forms:

- this corrects a Brainstack-owned universal defect
- this is the narrowest seam correction required so Brainstack can uphold its universal contract across installs

Any other kind of change is out of scope.

## required properties

### temporal grounding

- reminder-like or task-like content retrieved from Brainstack-managed state must not be surfaced as present or upcoming truth without current temporal grounding
- expired reminder/task text must lose ordinary-turn authority unless explicitly revalidated
- semantic relevance alone must not be enough to restore reminder/task truth
- `task_memory` itself must not remain broad enough to absorb arbitrary planning prose or reflective boilerplate as open tasks
- execution must explicitly state whether Phase 60 temporal grounding is being enforced:
  - at durable-write time
  - at retrieval/projection time
  - or via a hybrid design
- execution must prefer existing explicit Brainstack task/operating structures before widening temporal logic across generic transcript/continuity evidence

### provenance and trust

- assistant-authored self-diagnosis, self-congratulation, self-reported fixes, or speculative implementation narrative must not be promoted into durable continuity/decision/profile truth without stronger grounding than ordinary user text requires
- user-authored truth, tool-grounded truth, and assistant-origin narration must be distinguishable at durable-write time
- preserved user complaints about seeing something are not equivalent to proof that the assistant truly emitted that exact line in a preserved artifact
- execution must explicitly account for the current merged-turn transcript model, where Tier-2 extraction reads transcript rows containing both user and assistant text
- explicit structured task capture must require an actually task-shaped user declaration, not any multi-line prose block that merely contains task cues

### reflection-path hygiene

- reflection-triggered memory/skill writes must not be treated as ordinary user-authored conversation truth by Brainstack durable extraction
- if reflection-driven writes remain by design, their durable trust level must be bounded and explicit
- ordinary Discord use must not silently mutate durable Brainstack state through reflection paths in a way that later masquerades as user-established truth
- if the current host does not expose explicit reflection-source metadata to Brainstack, Phase 60 may request only the thinnest seam required to provide that metadata

### scheduler/config narrative hygiene

- scheduler or pulse configuration claims must not become durable Brainstack truth merely because they were narrated confidently in a noisy turn
- if a live scheduler mutation is persisted or resurfaced through Brainstack, that persistence must be justified by explicit authority and provenance, not semantic similarity

### minimal seam discipline

- host/runtime code may only be touched if the evidence proves that Brainstack correctness cannot be preserved otherwise
- the wizard may only change if reproduction or installability of the Brainstack fix requires it
- even when a seam change is justified, it must remain thin and upstream-survivable

## explicitly allowed change shapes

- Brainstack extraction filters
- Brainstack durable-write gating
- Brainstack provenance/trust classification
- Brainstack temporal-evidence gating
- Brainstack continuity/transcript selection rules
- Brainstack installer changes narrowly required to preserve the above across fresh installs

## explicitly disallowed change shapes

- broad Hermes cron redesign
- generic gateway UX cleanup
- generic Discord adapter cleanup
- generic execute_code/background-process cleanup
- one-off prompt band-aids targeting this user's exact wording
- Hungarian-specific heuristics
- deletion of broad historical state just to remove visible symptoms
- any change whose only defense is "it fixed the current thread"

## proof expectation

The execution result must prove all of the following:

1. what defect was universal and Brainstack-owned
2. what evidence from the case study supported that conclusion
3. what was intentionally left as host/runtime boundary
4. why the implemented change is minimal
5. why the same logic would still make sense for another user and another reminder/task path

## anti-goals

- no sebtapasz
- no fake closure from one cleaned-up replay
- no ownership laundering where a host problem is renamed into a Brainstack issue
- no architectural drift into a generic Hermes stabilization phase
