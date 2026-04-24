# Phase 14 Summary

## What Changed
- Added stronger real-world recall proving coverage in the Brainstack source repo:
  - `/home/lauratom/Asztal/ai/atado/Brainstack/tests/test_brainstack_real_world_flows.py`
- Proved the installed Bestie runtime against everyday memory behaviors with a runtime proof harness:
  - `/home/lauratom/phase14_runtime_proof.py`
- Closed a deeper host-side half-wire family in the live Hermes runtime:
  - legacy `memory` and `session_search` tool paths were still reachable even with Brainstack configured as the sole memory provider
  - session boundary paths still had legacy builtin-memory flush behavior
- Added a dedicated Brainstack-only host gate in the installed runtime:
  - `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest/agent/brainstack_mode.py`
- Wired the host gate into the installed runtime so:
  - `run_agent.py` removes legacy memory/search tools from the live tool surface
  - `gateway/run.py` routes reset / resume / expiry boundaries through Brainstack-aware finalization
  - maintenance agents stop carrying legacy memory toolsets in Brainstack-only mode
- Carried the same host-side fix into the Brainstack integration kit:
  - `/home/lauratom/Asztal/ai/atado/Brainstack/host_payload/agent/brainstack_mode.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack/scripts/install_into_hermes.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack/scripts/brainstack_doctor.py`

## Core Phase-14 Decisions
- Treated the Discord symptom as a host-boundary bug family, not as a one-off prompt or extractor defect.
- Kept the single Brainstack runtime path:
  - no second runtime
  - no fallback builtin-memory owner
  - no visible memory/search tools in Brainstack-only mode
- Fixed the host boundary in both places that matter:
  - the currently installed Bestie runtime
  - the Brainstack integration kit that installs into future Hermes updates
- Kept the proving scope practical:
  - real-world recall behavior
  - host half-wire elimination
  - installed-runtime proof
  - no broad speculative test explosion

## Anti-Half-Wire Proof
- The live Bestie runtime now reports Brainstack-only host mode and no legacy memory/search tool exposure from inside the running container.
- The installed runtime test coverage now includes:
  - `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest/tests/run_agent/test_brainstack_only_mode.py`
  - `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest/tests/gateway/test_flush_memory_stale_guard.py`
- The Brainstack integration kit now dry-runs the host carry-forward against an unpatched Hermes checkout instead of only validating already-fixed live runtime state.

## Local Verification
- Brainstack real-world flow tests passed in the source repo:
  - `17 passed in 1.89s`
- Installed-runtime host boundary tests passed:
  - `14 passed in 1.68s`
- Broader affected Hermes host suite passed:
  - `269 passed in 4.40s`
- Brainstack installer dry-run and doctor checks now prove host carry-forward for a fresh Hermes checkout.

## Installed Runtime Verification
- Runtime proof passed for everyday memory behaviors:
  - focus preference survives ordinary follow-up
  - shared work context survives ordinary follow-up
  - relationship recall is available, not only flat fact recall
  - corrected current state wins by default while prior state remains queryable
- Discord-visible legacy `memory:` / `session_search:` behavior was traced to real host wiring and closed at the host boundary, not hidden with a prompt workaround.

## Outcome
Phase 14 turned the earlier Brainstack build into a more believable everyday runtime:
- recall proving now covers normal conversational drift instead of only synthetic shelf-level tests
- the live host now behaves like Brainstack is the single memory owner
- the same host-only contract now survives future Hermes refreshes through the integration kit instead of living only in one patched checkout
