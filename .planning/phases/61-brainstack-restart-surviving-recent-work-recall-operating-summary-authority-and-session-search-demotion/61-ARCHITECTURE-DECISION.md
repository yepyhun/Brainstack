## Phase 61 Architecture Decision

### Frozen decisions

1. Recent-work restart recall stays Brainstack-owned.
   - No new host-side recap tool or special `/resume` dependency was introduced.
   - `session_search` remains secondary transcript-detail recovery only.

2. Task and operating understanding now use structured model output instead of cue lists.
   - `task_memory.py` and `operating_truth.py` now delegate query/capture understanding to `structured_understanding.py`.
   - `control_plane.py` consumes the structured route payload instead of local phrase parsing.

3. Recent-work recap authority stays principal-scoped operating truth with session provenance.
   - `active_work` can be captured during ordinary sync when the user explicitly provides durable operating truth.
   - `recent_work_summary` and `open_decision` are consolidated from continuity into `operating_records`.
   - The recap answer path now prefers `operating_records` over transcript/session search.

4. Prefetch stays read-only.
   - `prefetch()` no longer runs task/operating capture inference on the query text.
   - Read-time recap routing must not mutate durable state.

5. Active query/capture heuristics were removed from the recent-work kernel path.
   - Old task/operating cue tables and phrase parsers are gone.
   - The native aggregate phrase-planner was disabled instead of preserved as a hidden exception.
   - The live Tier-2 logistics regex supplement was removed; only DB migration compatibility code still references it.

6. No new Phase 61 host seam was added.
   - The existing Phase 60 write-origin bridge remains, but Phase 61 introduced no new Hermes patch surface.

### Explicit anti-decisions

- No Hungarian or English recap keyword farm.
- No exact-phrase rescue for `phase 60`.
- No `session_search` timeout tuning presented as the core fix.
- No transcript dump fallback masquerading as durable recall.
- No session-end-only design; recent-work operating truth must exist before transcript fallback becomes necessary.
