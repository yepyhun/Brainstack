# Phase 12 Context

## Goal
Attach a real Tier-2 multilingual extractor and deterministic reconciler to the Brainstack ingest pipeline without breaking the single-provider architecture or the Hermes non-blocking `sync_turn()` contract.

## Why This Phase Exists
- Phase 10.2 stopped durable ingest noise.
- Phase 11 created explicit Tier-0 / Tier-1 / Tier-2 scheduling seams.
- Live Discord proof still shows the practical gap:
  - profile gets only shallow heuristic facts
  - graph is structurally present but underfilled
  - continuity is still closer to turn logging than durable topic/decision extraction
- The next step is not more regex. It is multilingual semantic extraction plus deterministic reconciliation.

## Host Contract Truth
- Hermes `MemoryProvider.sync_turn()` is explicitly documented as non-blocking.
- If Tier-2 extraction has network or model latency, the provider must queue/background that work instead of blocking the user-facing turn path.
- `on_session_end()` may do bounded flush work because it is not on the live reply path.

## Architecture Decision
Phase 12 uses a **single Brainstack provider with one bounded background worker path**.

### Chosen Direction
- Keep one provider and one SQLite-backed Brainstack store.
- Reuse the existing Tier-2 scheduling seam from Phase 11.
- When Tier-2 scheduling triggers inside `sync_turn()`:
  - do not block
  - start or notify one daemon worker path
- Run the actual Tier-2 extract + reconcile work in that background path.
- Use a deterministic reconciler:
  - `ADD`
  - `UPDATE`
  - `NONE`
  - `CONFLICT`
- Reuse Hermes auxiliary LLM routing instead of inventing a separate raw client stack.

### Required Background-Worker Rules
- one worker path at a time per provider instance
- no dropped work if new turns arrive while a worker is already running
- hard timeout on the Tier-2 model call
- session-end flush must first wait for any running worker, then flush remaining pending work
- worker failure must release the running state so the next trigger can recover

## Phase Boundary
This phase is about **multilingual extraction and reconciliation**, not new storage layers.

In scope:
- Tier-2 extractor module
- deterministic reconciler module
- provider-side background-worker wiring
- non-blocking `sync_turn()` scheduling
- bounded `on_session_end()` flush
- profile / graph / continuity writes from reconciled Tier-2 output
- targeted tests that prove:
  - no user-visible sync blocking from Tier-2 work
  - no dropped batches while worker is active
  - reconciler dedupes / updates / conflicts correctly
  - session-end flush closes remaining pending work

Out of scope:
- corpus semantic extraction
- new memory layers
- provider tool surface changes
- large async orchestration systems
- adaptive usefulness scoring
- Phase 13 temporal/provenance donor adoption

## Extractor Requirements
- multilingual by model prompt, not by growing language-specific regexes
- bounded transcript batch input
- structured output only:
  - `preferences`
  - `states`
  - `relations`
  - `shared_work`
  - `continuity_summary`
  - `decisions`
- fake/injected extractor path for deterministic tests

## Reconciler Requirements
- preferences / shared work:
  - dedupe stable repeats
  - upsert durable profile items
- graph states:
  - unchanged -> `NONE`
  - new current state -> `UPDATE` via supersession where appropriate
  - incompatible claim without supersession -> `CONFLICT`
- relations:
  - no duplicate repeated edge spam
- continuity summary / decisions:
  - written as bounded continuity artifacts, not as raw turn spam

## Anti-Half-Wire Requirements
- Tier-2 must use the live Phase 11 scheduling seam, not a parallel hidden path.
- The background path must write through the same Brainstack store API, not a side database or temp cache.
- The installed Bestie runtime must exercise the same provider path as the source repo tests.
- A passing unit test is not enough; installed-runtime proof must show actual background Tier-2 writes land in the intended shelves.

## Canonical References
- `.planning/STATE.md`
- `.planning/ROADMAP.md`
- `.planning/phases/11-extraction-pipeline-foundation/11-CONTEXT.md`
- `.planning/phases/11-extraction-pipeline-foundation/11-01-PLAN.md`
- `.planning/phases/12-tier-2-multilingual-extractor-and-reconciler/12-ARCHITECTURE-NOTES.md`
- `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/__init__.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/extraction_pipeline.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/db.py`
- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest/agent/memory_provider.py`
- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest/agent/auxiliary_client.py`

## Output Expectation
After this phase:
- `sync_turn()` remains non-blocking
- Tier-2 can actually enrich profile / graph / continuity from multilingual user text
- duplicates and stale overwrites are bounded by reconciliation
- the system is ready for Phase 13 temporal/provenance hardening instead of more ingest surgery
