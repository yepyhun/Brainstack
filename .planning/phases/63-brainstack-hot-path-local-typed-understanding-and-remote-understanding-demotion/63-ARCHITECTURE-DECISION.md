# Phase 63 Architecture Decision

## frozen decision

Do not roll back to `v1.0.16`, and do not restore cue-list or phrase-farm routing.

Instead, replace ordinary Brainstack task/operating hot-path authority with a local deterministic typed-understanding layer:

1. read path
   - no mandatory remote query classification for ordinary task/operating recall
   - use explicit typed envelopes when present
   - otherwise probe typed Brainstack state locally:
     - task rows from local task search
     - operating rows from local operating search and bounded current-record fallback
   - absent explicit typed route payload, ordinary route stays `fact`

2. capture path
   - no semantic hot-path capture from plain natural-language turns
   - only explicit typed envelopes can create task/operating captures on the ordinary path
   - this keeps capture deterministic, typed, and multimodal-compatible

3. remote understanding
   - demoted from ordinary hot-path authority
   - no config-backed remote route resolver in ordinary packet building
   - any future model-based understanding must remain bounded and off-path

## accepted rationale

- this removes the remaining critical hot-path dependence identified after Phase `61.1`
- it preserves the no-heuristic rule instead of sneaking in local cue routing
- it keeps the design compatible with future multimodal typed envelopes instead of binding the kernel to raw text heuristics
- it makes ordinary packet behavior availability-safe without pretending transcript/tool fallback is a memory-kernel fix

## explicit anti-decisions

- no rollback to pre-`v1.0.17` heuristic routing
- no locale dictionaries, cue lists, or renamed keyword farms
- no reintroducing remote semantic capture in `sync_turn(...)`
- no hidden host-side classifier as a substitute for Brainstack-owned local authority
- no route-resolver timeout tuning presented as an architectural fix
