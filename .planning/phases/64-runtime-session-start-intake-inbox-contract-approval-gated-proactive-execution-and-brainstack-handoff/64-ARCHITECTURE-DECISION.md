# Phase 64 Architecture Decision

## decision

Land a bounded runtime-side `policy consumer + typed session-start intake + explicit task writeback` slice.

This execute cut does **not** turn Hermes into a hidden autonomous executor and does **not** move governance into Brainstack.

## landed runtime pattern

- Hermes runtime reads explicit JSON inbox envelopes at session start.
- Hermes mirrors those envelopes into Brainstack through Brainstack-owned provider APIs.
- Hermes injects a bounded read-only session-start context block built from:
  - canonical policy
  - runtime approval policy
  - live system state
  - pending runtime handoff tasks
- Hermes exposes a typed `runtime_handoff_update` tool through the Brainstack provider for intentional task status writeback.
- Completed/failed/cancelled/stale tasks move to `outbox`; active or blocked tasks stay in `inbox`.

## ownership

- Brainstack remains:
  - policy/state authority
  - typed handoff state store
  - writeback API owner
- Hermes runtime remains:
  - intake consumer
  - ephemeral startup orchestrator
  - execution actor when explicitly approved by task metadata and policy
- this execute cut does **not** make Hermes the hidden owner of transcript-derived policy or free-text task inference

## inbox contract rule

The runtime consumer accepts only explicit typed envelopes. It does not recover tasks from roadmap prose, transcript residue, or loose natural language.

## approval rule

Approval policy is seeded and consumed as explicit metadata. The writeback tool blocks start/completion of approval-required tasks unless `approved_by` is explicitly present.

## writeback rule

The landed write path is `runtime -> Brainstack provider tool -> typed handoff state + inbox/outbox JSON state`.

This is not direct DB mutation and not transcript reconstruction.

## paired live stabilization

The runtime consumer slice required two live stabilizations:

- remove the invalid Tier-2 request-contract shape that still triggered `400 Invalid input`
- bound the startup compression hot path so session-start work does not stall behind long auxiliary/provider churn

## rejected alternatives

- transcript scraping as session-start recovery
- roadmap/markdown keyword routing as task authority
- direct runtime-to-DB writes
- free-text domain classification in the runtime handoff consumer
- keeping completed tasks in the session-start pending snapshot
