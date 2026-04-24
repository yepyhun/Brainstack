# Phase 22 Implementation Contract

## Objective

Clarify and, where justified, improve the Brainstack/native Hermes capability boundary without creating unnecessary new maintenance or replacing native features that already serve a different job well.

## System doctrine this phase must preserve

- Brainstack remains the owner of durable personal-memory truth.
- Native Hermes capabilities are not to be displaced just because they are memory-adjacent.
- Coexistence is acceptable when the capability classes are different and the boundary stays explicit.
- Overengineering is a failure condition for this phase.
- The project guardrails remain active and must be used as decision criteria:
  - donor-first
  - modularity / upstream updateability
  - truth-first
  - fail-closed on the owned axis
  - no benchmaxing
  - no overengineering

## Workstream A: Capability-boundary truth

- Establish the real capability map for:
  - Brainstack durable memory
  - `session_search`
  - native automation / `cronjob`
  - host context shell
  - legacy built-in memory
  - plugin memory orchestration

Required artifact:

- one owner/coexistence matrix that classifies each capability by role

## Workstream B: `session_search` boundary decision

- Prove whether `session_search` is:
  - a competing owner
  - or a separate transcript-forensics capability
- If it is separate, prefer bounded coexistence over blanket suppression.
- If it is competing, keep it hidden and state why clearly.

Protected rule:

- do not decide this by intuition or by the word "memory" alone

## Workstream C: Memory orchestration clarity

- Reconcile the real runtime layering between:
  - legacy built-in memory in `run_agent.py`
  - plugin memory via `MemoryManager`
- Prefer the thinnest change that makes runtime and docs tell the same architectural story.

Protected rule:

- do not launch a broad orchestration refactor unless the truth pass proves the current split is actively causing the boundary bug

## Workstream D: Proof

- Verify that:
  - Brainstack still owns the durable personal-memory axis
  - native cron remains usable outside that axis
  - any `session_search` decision is reflected honestly in runtime behavior
  - the orchestration story is clearer after the phase than before it

Required proof shape:

- one capability-boundary artifact
- one runtime proof for the chosen `session_search` decision
- one architecture-clarity proof or explicit no-change verdict

## Workstream E: User-facing decision checkpoints

- If the execute reaches a real architecture fork, present it back to the user:
  - in simple language
  - with short tradeoffs
  - with a direct recommendation and reason
- Do not lock the final direction silently when there is a real product choice.

## Protected boundaries

### Anti-overengineering boundary

- No new broad framework
- No “replace everything with Brainstack” answer
- No host-monolith cleanup campaign hiding inside this phase

### Compatibility / donor-risk boundary

- Do not restore `session_search` as a second durable personal-memory owner.
- Do not weaken the current cron/automation ownership guard on the personal-memory axis.
- Do not broaden host context shell inputs into shadow owners again.
- Do not turn the memory orchestration clarity problem into a large rewrite unless the execute truth proves that is the only correct path.

### Donor-first boundary

- Prefer narrow coexistence and clear ownership over custom replacement work.
- Keep useful upstream-native capabilities where they already solve a different problem well.

### Truth boundary

- Decide by capability class and actual runtime behavior.
- Do not confuse transcript forensics with durable personal memory.
- Do not confuse documentation drift with proof that a large refactor is required.

## Minimum evidence required before calling Phase 22 done

- explicit capability owner/coexistence matrix
- explicit `session_search` verdict with rationale
- explicit runtime/docs orchestration verdict
- proof that Brainstack ownership on the personal-memory axis still holds
- user-facing checkpoint(s) used for any real architecture fork encountered during execute
