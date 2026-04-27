# Non-Goals And Known Limits

## Non-Goals

- No claim that Brainstack is bug-free in every environment.
- No support for arbitrary unmounted host filesystem access.
- No web browsing success claim when backend/env/key is unavailable.
- No Brainstack-owned output governor, tool governor, approval governor, or runtime scheduler.
- No hardcoded live-case blacklist such as observed persona phrases.
- No Hungarian-specific durable write parser.
- No raw transcript deletion as correctness proof.
- No feature expansion during GA hardening unless required to close P0/P1.

## Known Limitation Policy

Every known limitation must include:

- limitation id;
- affected use case;
- user-facing risk;
- mitigation;
- why it does not block GA;
- exact condition where it becomes P0/P1 blocker.

Known limitation cannot hide:

- capability shrink;
- approval bypass;
- support-only leakage into answer truth;
- assistant self-contamination refeed;
- URL/file/web guessing without evidence;
- source/wizard/Docker mismatch;
- manual-only proof.

## Current Known Limit

```json
{
  "id": "live_discord_smoke_not_run",
  "affected_use_case": "Discord live product confidence",
  "user_facing_risk": "unknown live integration drift",
  "mitigation": "Phase 185 keeps ready=false and emits P1 live_gate failure bundle",
  "does_not_block_local_docker_rc": true,
  "blocks_ga_ready": true,
  "would_block_ga_if": "live Discord remains part of supported GA scope"
}
```
