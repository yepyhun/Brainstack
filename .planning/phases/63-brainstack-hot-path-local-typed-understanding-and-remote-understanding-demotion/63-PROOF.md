# Phase 63 Proof

## source proof

Green compile:
- `brainstack/local_typed_understanding.py`
- `brainstack/db.py`
- `brainstack/task_memory.py`
- `brainstack/operating_truth.py`
- `brainstack/control_plane.py`
- `brainstack/executive_retrieval.py`
- `brainstack/__init__.py`

### source temp-harness proof

With a temporary Brainstack store containing:
- one task row: `Finish phase 63 report`
- one operating row: `active_work = Stabilizing Brainstack Phase 63 hot path.`

The local typed-understanding path returned:
- `task_probe_found = true`
- `operating_probe_found = true`

The ordinary packet builder returned:
- `packet_task_rows = 1`
- `packet_operating_rows = 1`
- `packet_route.requested_mode = fact`
- `packet_route.applied_mode = fact`
- `packet_route.source = fact_default`
- `packet_route.resolution_status = skipped`

Explicit-only capture proof:
- explicit structured task capture -> success
- plain natural-language task capture -> `null`
- explicit structured operating capture -> success
- plain natural-language operating capture -> `null`

## live-target proof

Target:
- `/home/lauratom/Asztal/ai/veglegeshermes-source`

### live carry-forward

Carried to live plugin payload:
- `plugins/memory/brainstack/local_typed_understanding.py`
- `plugins/memory/brainstack/db.py`
- `plugins/memory/brainstack/task_memory.py`
- `plugins/memory/brainstack/operating_truth.py`
- `plugins/memory/brainstack/control_plane.py`
- `plugins/memory/brainstack/executive_retrieval.py`
- `plugins/memory/brainstack/__init__.py`

After the final rebuild:
- container health: `healthy`
- restart count: `0`

### container proof

Inside the live container, with the same temp-store harness:
- `task_probe_found = true`
- `operating_probe_found = true`
- `packet_task_rows = 1`
- `packet_operating_rows = 2`
  - one `active_work`
  - one `live_system_state`
- `packet_route.source = fact_default`
- `packet_route.resolution_status = skipped`
- explicit structured capture succeeds
- plain natural-language capture returns `null`
- no parser warning noise remained after the final `local_typed_understanding.py` guard fix

## regression proof

Focused live regression ring after the final rebuild:
- `265 passed, 8 warnings in 7.58s`

Ring:
- `tests/agent/test_memory_provider.py`
- `tests/run_agent/test_memory_provider_init.py`
- `tests/tools/test_session_search.py`
- `tests/cron/test_jobs.py`
- `tests/cron/test_scheduler.py`
- `tests/cron/test_cron_inactivity_timeout.py`
- `tests/gateway/test_flush_memory_stale_guard.py`
