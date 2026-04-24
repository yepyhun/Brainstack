# Phase 60 Hard Gates

Phase 60 is not complete unless all of the following are true.

## 1. Brainstack-only gate

- the final result clearly states which Phase 60 findings are Brainstack-owned universal defects
- the final result clearly states which findings remain Hermes host/runtime boundary issues
- no host/runtime issue is "fixed" under Phase 60 unless a narrow Brainstack seam need explicitly justified it

## 2. Case-study discipline gate

- the execution result does not speak as if the user's current thread were the design target
- the final diagnosis is written in universal failure-mode language, not in one-thread anecdote language
- at least one acceptance statement explicitly checks that the fix is not tied to this exact reminder wording, this exact time, or this exact user path

## 3. Temporal-grounding gate

- expired reminder/task text stored in Brainstack-managed state can no longer surface in an ordinary turn as present or upcoming truth without current grounding
- the proof distinguishes semantic relevance from temporal authority
- the closeout states which Brainstack lane(s) the fix covered first:
  - `task_memory`
  - `operating_truth`
  - transcript/continuity resurfacing
  - or a justified subset
- structured task memory itself must no longer accept arbitrary planning prose or reflection prompts as open tasks just because task cues appear somewhere in the text

## 4. Provenance/trust gate

- assistant-authored self-diagnosis, self-reported fixes, and speculative implementation narration no longer cross into durable Brainstack truth under the same evidence class as user or tool-grounded facts
- preserved user reports of seeing something are not misclassified as durable proof that the assistant really emitted that exact line

## 5. Reflection-path gate

- if reflection-driven writes remain active, their durable trust treatment is explicitly bounded
- if they do not remain active, the result says where they were cut off
- in either case, ordinary user conversation can no longer silently feed the same durable contamination path under the current evidence class
- if a thin host seam was required to expose reflection-source metadata, the result explains why Brainstack correctness could not be preserved without it

## 6. Scheduler/config contamination gate

- live scheduler/pulse configuration drift is only addressed in Phase 60 to the extent that Brainstack persists, projects, or over-trusts it
- the phase does not expand into generic scheduler redesign
- any retained live pulse configuration is either explicitly classified as outside Brainstack scope or shown not to contaminate Brainstack durable truth

## 7. No-sebtapasz gate

- there is no exact-phrase hack
- there is no user-specific patch
- there is no locale-specific rescue logic
- there is no prompt-only disguise that leaves the underlying evidence path intact

## 8. Source-of-truth gate

- any code change lands first in:
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`
- any installed proof is reproduced on:
  - `/home/lauratom/Asztal/ai/veglegeshermes-source`

## 9. Truth-first closeout gate

- the phase closeout does not use blended language like "it was kind of everything"
- it names:
  - what was Brainstack
  - what was not Brainstack
  - what seam changes, if any, were strictly required
  - what residual non-Brainstack issues remain
- it also names the frozen pre-execution architecture choice for:
  - temporal grounding
  - provenance/trust
  - reflection-path handling
