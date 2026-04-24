# Phase 61 Context

## why this phase exists

The live system just exposed a direct violation of what a memory kernel is supposed to do.

After restart, the user asked for a broad recap of the immediately preceding Brainstack work. Brainstack should have answered from durable state. Instead:
- Brainstack produced an effectively empty recall packet
- the model escalated to `session_search`
- `session_search` then blocked the turn badly enough to become the visible failure

That means the root problem is not merely that `session_search` was too slow. The root problem is that Brainstack failed to provide the recap memory it should have provided before transcript search was even considered.

## current live facts

### 1. Brainstack is active

Live config shows:
- memory provider is Brainstack
- Brainstack plugin config is present
- sidecar RTK is disabled

This means the current failure is not explained by "Brainstack was off".

### 2. relevant recent-work data exists in Brainstack-managed storage

The live DB contains `phase 60`-related rows in:
- `continuity_events`
- `transcript_entries`

Examples include:
- explicit `Phase 60` references
- decisions to discard or abandon `Phase 60`
- transcript rows from the live thread discussing the cleanup

So the problem is not simply "nothing was stored".

### 3. the durable recent-work lane is under-populated

The same live DB currently shows no useful `operating_records` for `Phase 60`.

That is the first concrete architectural gap:
- continuity and transcript contain relevant recent-work material
- operating truth does not carry a useful recap-ready summary of it

Important current architecture fact:
- `operating_records` already uses principal-scoped ownership with session provenance
- the table already carries:
  - `principal_scope_key`
  - `source_session_id`
  - `source_turn_number`

So Phase 61 does not need to reopen "session-scoped or principal-scoped?" as a blank-slate design question. The intended model is already principal-scoped truth with session-level provenance.

### 4. the recap packet is effectively empty

When the real restart recap question is run through the live Brainstack packet builder with the correct user scope, the result is still effectively empty:
- `continuity_rows = 0`
- `operating_rows = 0`
- `task_rows = 0`
- `transcript_rows = 0`
- only one profile row survives

That is the second concrete architectural gap:
- even where relevant state exists somewhere in Brainstack-managed storage, the retrieval route is not surfacing it

### 5. transcript FTS can still find relevant evidence for simpler queries

Live transcript FTS can return useful rows for normalized queries like:
- `phase 60`
- `phase 60 brainstack`
- `brainstack`

So the third gap is:
- not pure storage absence
- not pure DB corruption
- but recall routing / query shaping / projection failure for broad recap questions

### 6. recap is not task lookup

The existing Brainstack `task_like` route is already a separate structured lane for obligation-style asks such as:
- what do I need to do tomorrow
- what is my task list

That is not the same thing as recap questions such as:
- what were we doing
- what did we fix
- what landed before restart

Phase 61 must therefore add or refine a separate recap-recall route. It must not stretch the task-memory route until the two semantics blur together.

## current generalized defect statement

The current universal defect is:

**Brainstack does not yet provide a robust restart-surviving recent-work recall path for broad recap queries.**

More concretely:
- major recent work remains trapped in continuity/transcript lanes
- durable operating truth is too weak for recap use
- recap retrieval is too literal and too query-fragile
- transcript search is being used as a substitute for a proper recent-work memory lane

## why this is Brainstack-owned

This is Brainstack-owned because:
- the data path under discussion is Brainstack-managed storage and Brainstack packet assembly
- the empty result happened before any transcript-search tool had a chance to help
- the failure remains even when the correct principal scope is used
- the central defect is "what Brainstack chose to preserve and surface", not "whether Hermes has a search tool"

## why `session_search` is only a symptom here

The live failure looked like:
1. user asks a broad restart recap question
2. Brainstack provides no useful recap packet
3. model falls back to transcript search
4. transcript search hangs or becomes too expensive

So `session_search` is not the memory kernel. It is only a heavy transcript recall tool.

If Brainstack had surfaced a compact recent-work summary first, the visible failure path might never have triggered.

## sidecar note

Current live config:
- `sidecars.rtk.enabled: false`

This does not by itself prove a defect.

Phase 61 should not start from the assumption that enabling a sidecar is the answer. The first obligation is to make the main Brainstack kernel satisfy the recent-work recap contract using its own durable structures.

## what the next execution must decide

### 1. where recent-work truth should live

The preferred answer is:
- existing `operating_records`
- existing `operating_context`
- existing compact continuity support

Not:
- a giant transcript dump
- a second memory owner
- a sidecar-first workaround

### 2. what counts as recap-worthy work

The phase must define how Brainstack preserves:
- active work
- major completed outcomes
- meaningful discard/abandon decisions

without preserving:
- scratchpad chatter
- every intermediate step
- assistant bravado
- transient logs

This also implies a promotion-timing decision:
- session-end consolidation alone is likely too weak
- the live failure happened in a restart/interrupt-heavy path
- therefore the phase should assume bounded ongoing recent-work promotion may be required, with session-end consolidation as the second step rather than the only step

### 3. how recap questions are routed

The retrieval layer needs a bounded recent-work recap route.

It must be broad enough to handle natural recap wording after restart, but tight enough to avoid becoming a heuristic swamp.

It also must remain distinct from:
- `task_like`
- `operating_like`

even if it later reuses the same `operating_truth` substrate for projection.

### 4. when transcript evidence is still allowed

Transcript evidence should remain available, but only:
- after operating truth
- after compact continuity recap
- and only in bounded form

It must not become the default answer format for ordinary recap asks.

## non-goals to reject

Reject the following false fixes:
- "make session_search faster and call it solved"
- "store the whole previous thread in memory"
- "hardcode `phase 60` as a recall synonym"
- "special-case Hungarian recap wording"
- "enable a sidecar and hope it masks the gap"
- "treat profile memory as a substitute for recent-work memory"

## source-of-truth rule

Any implementation must land first in:
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`

Any proof must then be reproduced on:
- `/home/lauratom/Asztal/ai/veglegeshermes-source`
