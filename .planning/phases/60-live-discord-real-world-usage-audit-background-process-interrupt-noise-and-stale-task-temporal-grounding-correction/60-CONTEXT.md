# Phase 60 Context

## why this phase exists

Real Discord usage exposed a mixed failure cluster. The user explicitly narrowed the architectural intent after the initial audit:

- do not treat this as a Hermes bugfix phase
- do not optimize for this one live thread
- do use the thread as a case study for Brainstack-universal defects

That instruction is now part of the phase contract.

## case-study rule

The current live thread is input evidence only.

It is valid for:
- reproducing failure patterns
- identifying over-trusted evidence classes
- identifying missing temporal/provenance gates
- identifying Brainstack durable-write contamination paths

It is not valid for:
- shaping reply logic to this user's exact wording
- proving a Brainstack defect merely because the thread looked ugly
- widening the phase into Hermes cleanup

## accepted ownership model

### Brainstack-owned

Brainstack owns universal failures in:
- durable extraction
- evidence selection
- transcript/continuity/projection trust
- temporal grounding of retrieved reminder/task-like content
- provenance handling for assistant-authored claims
- durable promotion of speculative implementation narrative

### host/runtime-owned

Hermes host/runtime owns:
- generic execute_code interruption chatter
- generic background-process completion chatter
- generic provider fallback noise
- generic scheduler mechanics unless Brainstack specifically amplifies or persists their byproducts
- generic Discord adapter behavior

### wizard seam

The installer/wizard is only in scope when:
- Brainstack correctness across fresh installs depends on a seam
- the seam is already Brainstack-managed
- not patching it would break Brainstack's universal contract

### mixed

A mixed issue is only Brainstack-relevant here if the Brainstack portion can be separately stated and corrected.

## accepted evidence summary

### 1. stale temporal resurfacing is real

- the `11:15 van, indulnod kell elvinni a kaját` statement was not grounded in active scheduler truth when it resurfaced
- stale reminder text still existed in session/transcript/continuity artifacts
- therefore the user-visible wrong claim exposed a Brainstack-relevant temporal-grounding problem, not merely a fresh cron rerun

### 2. assistant-authored contamination is real

- assistant-authored self-diagnosis and self-declared fixes were promoted into durable continuity state
- assistant-authored speculative operational claims were also promoted
- therefore Brainstack is currently over-trusting assistant-origin narrative under some noisy live conditions

### 3. reflection-driven durable writes are real

- ordinary Discord sessions received reflection prompts
- those reflection paths caused real memory/skill writes
- therefore post-turn reflection is not just invisible bookkeeping; it is a state-mutating input stream

### 4. scheduler/config drift matters only through the Brainstack lens

- the active live cron state now includes a much more aggressive 2-minute `Brainstack Dynamic Pulse (SOTA)` job
- that drift is not automatically a Brainstack bug
- it becomes Phase 60-relevant when Brainstack:
  - persists it as trusted durable fact
  - projects it as ordinary-turn truth
  - uses it to justify further durable writes or authority claims

### 5. host noise remains real but bounded out of scope

- execute_code/background-process churn is real
- empty-after-tools nudging is real
- provider/runtime failures are real
- these matter only insofar as they create contaminated inputs that Brainstack later over-trusts

### 6. structured task memory can also be polluted

- live DB review showed that `task_memory` itself had absorbed a large multi-line planning/prose block as open tasks
- the immediate source was `sync_turn:task_memory`, not the host scheduler
- therefore Phase 60 cannot stop at "prefer task_memory over transcript"; it also has to ensure the structured lane is not populated by arbitrary planning prose

## generalized Brainstack defect statements

The user thread currently supports the following universal Brainstack defect statements:

1. Expired reminder/task language can remain eligible for ordinary-turn truth projection after it should have lost temporal authority.
2. Assistant-authored narrative can cross the trust boundary and become durable continuity/decision state without adequate external grounding.
3. Reflection-generated writes are not treated as high-risk or specially bounded inputs when durable Brainstack state is formed.
4. Scheduler/configuration narrative can become durable "system truth" too easily when it originated in noisy mixed turns.
5. Structured `task_memory` capture can over-accept planning prose or reflective boilerplate and turn it into open tasks.

These statements are universal enough to matter for another user, another language, or another task domain.

## execution risk notes

### 1. temporal-grounding is not free

The plan cannot pretend that temporal grounding is already solved by one existing global filter.

Current architecture facts:
- Brainstack already has real `task_memory` and `operating_truth` lanes
- `task_memory` already stores explicit due-date/date-scope structure
- generic transcript/continuity resurfacing still exists separately

Execution implication:
- Phase 60 should first target temporal authority where the architecture already has explicit task/operating structure
- if transcript/continuity resurfacing also needs temporal filtering, that must be justified carefully and not implemented as a keyword farm

### 2. provenance is partly present, partly missing

Current architecture facts:
- Brainstack already has generic provenance utilities and metadata plumbing
- session-end durable admission already rejects non-user role content
- but Tier-2 extraction currently reads merged turn transcript rows containing both `User:` and `Assistant:` content in one transcript entry

Execution implication:
- provenance/trust improvement is relevant
- but it is not a trivial "just add role tags" change at the extraction boundary
- the execution must explicitly choose how to preserve or reconstruct role/trust separation without broad heuristics

### 3. reflection handling may need a thin seam

Current architecture facts:
- live reflection prompts are explicit background review prompts in `run_agent.py`
- they mutate shared memory/skill stores
- no current evidence shows a clean explicit reflection flag arriving inside Brainstack durable extraction inputs

Execution implication:
- if Brainstack cannot safely distinguish reflection-generated writes from ordinary conversation-derived writes with current metadata, a thin host seam may be justified
- but only for explicit reflection-source metadata, not for generic host cleanup

## non-universal statements to reject

The phase must explicitly reject the following as design targets:

- "fix the 11:15 reminder sentence"
- "fix Hungarian reminder phrasing"
- "fix this exact Discord thread"
- "fix cron generally"
- "make background tools quieter no matter what"
- "make the pulse daemon hourly again" unless Brainstack ownership is proven

## design intent

### for Brainstack

- temporal validity must become a first-class part of evidence trust for reminder/task-like resurfacing
- assistant-authored claims must have a stricter durable-promotion threshold than user-authored truth or tool-grounded truth
- reflection-driven writes must be bounded, classified, or discounted so they do not silently contaminate durable state
- noisy operational narration must not turn into continuity/decision truth just because it is semantically relevant

### for host/runtime

- retain only boundary notes unless a narrow seam correction is required for Brainstack correctness
- do not reopen broad native surgery merely because the case study surfaced multiple messy symptoms

## source-of-truth rule

Any code fix must land first in:
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`

Any proof must then be reproduced on:
- `/home/lauratom/Asztal/ai/veglegeshermes-source`

## phase-wide anti-drift reminder

If later execution starts to look like a Hermes cleanup pass, the phase is off track.
