# Phase 64 Hard Gates

## hard-gate 1: ownership gate

The phase must not move scheduler or execution authority into Brainstack.

## hard-gate 2: no-heuristic gate

The runtime must not decide domain, risk, or approval status from cue lists, locale dictionaries, or renamed keyword routing.

## hard-gate 3: explicit-envelope gate

Inbox tasks must be explicit typed envelopes. Loose natural-language recovery is not a valid substitute.

## hard-gate 4: bounded-startup gate

Session-start intake must stay bounded and deterministic. No unbounded file crawling or transcript fishing.

The proof target must show cheap startup behavior, not just correctness in principle.

## hard-gate 5: approval-safety gate

Unknown or explicitly blocked domains must not execute automatically.

## hard-gate 6: anti-fake-autonomy gate

The resulting system must not claim continuous autonomous operation beyond what cron/session-start/runtime hooks really provide.

## hard-gate 7: writeback gate

Execution results must become typed durable state, not merely conversational narration.

Direct runtime-to-DB writeback that bypasses a Brainstack-owned seam is not allowed.

## hard-gate 8: generality gate

The resulting contract must be reusable for future proactive agents, not tied to one local folder layout or one user story.

## hard-gate 9: truth-first closeout

The phase closeout must separately name:

- what Brainstack supplies
- what Hermes runtime enforces
- what remains unsolved
