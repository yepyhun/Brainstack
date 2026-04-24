# Phase 15 Summary

## What Changed

- Added a Brainstack-owned retrieval usefulness helper:
  - `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/usefulness.py`
- Extended the store to record bounded retrieval telemetry on surfaced rows:
  - `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/db.py`
- Wired telemetry capture and modest adaptive ranking into the control plane:
  - `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/control_plane.py`
- Added focused regression coverage for the new telemetry and bounded ranking behavior:
  - `/home/lauratom/Asztal/ai/atado/Brainstack/tests/test_brainstack_usefulness.py`

## Core Phase-15 Decisions

- Telemetry is stored inside existing `metadata_json`, not in a new subsystem.
- The phase records what Brainstack actually surfaced into working memory.
- Profile rows distinguish:
  - matched retrieval
  - fallback / same-session retrieval
- Graph rows record matched retrieval telemetry by concrete row id.
- Ranking adjustments stay bounded and shelf-aware.
- Core identity, preference, and shared-work rows are protected from accidental demotion.
- The donor flat ratio logic was not transplanted as Brainstack's final scoring model.

## Local Verification

- Python compile passed for:
  - `brainstack/usefulness.py`
  - `brainstack/db.py`
  - `brainstack/control_plane.py`
  - `tests/test_brainstack_usefulness.py`
- A focused manual harness passed on source code and confirmed:
  - fallback-only non-core rows get a negative adjustment
  - core preference rows stay protected
  - graph rows gain a modest matched-use bonus
  - surfaced profile rows record retrieval telemetry
  - surfaced graph rows record retrieval telemetry
  - working-memory packets still render the communication contract and graph truth correctly

## Graph-Backed Sanity Check

- Code-review-graph incremental update succeeded on the Brainstack source repo.
- The changed-file review showed no new flow explosion and no sign of a second runtime or half-wire memory branch.
- The graph audit highlighted the new retrieval helpers as the main changed seam, which is expected for this phase.

## Installed Runtime Verification

- Reinstalled Brainstack into the live Bestie checkout through the integration kit and doctor:
  - doctor remained `PASS`
- A first live carry-through check showed the host checkout was updated but the running container was still on the old image.
- Root cause:
  - the machine reboot interrupted the force-recreate rebuild path
  - Docker came back up on the previously running image
- Closed this with a direct compose rebuild:
  - `docker compose -f docker-compose.bestie.yml up -d --build --force-recreate hermes-bestie`
- After the direct rebuild:
  - `/opt/hermes/plugins/memory/brainstack/usefulness.py` exists in the live container
  - `db.py` and `control_plane.py` in the live container contain the new telemetry hooks
  - gateway healthcheck inside the container reports `running; connected=discord`
- Live in-container proof passed:
  - communication contract still renders
  - profile telemetry increments on surfaced style facts
  - graph telemetry increments on surfaced graph truth rows

## Outcome

Phase 15 gives Brainstack its first bounded adaptive recall layer without changing the architecture:

- surfaced memory now leaves telemetry behind
- repeated matched rows can gain a modest edge
- repeated fallback-only non-core rows can be gently deprioritized
- core personal and shared-work memory remains protected
- the logic survives install/rebuild because it lives in the Brainstack source and integration path
