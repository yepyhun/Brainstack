---
status: complete
phase: 10-structured-donor-boundary-and-refresh-workflow
source:
  - 10-01-SUMMARY.md
  - 10-UAT.md
started: 2026-04-10T18:21:15Z
updated: 2026-04-10T18:21:15Z
---

# Phase 10 Security Review

## Scope

Review the new donor registry and bounded refresh workflow introduced in Phase 10 for:
- silent second-path behavior
- unsafe registry-driven path resolution
- fail-open refresh/reporting behavior
- misleading update surface claims

## Findings

### 1. Unknown donor selection could fail open in the refresh script
- Risk: A mistyped or invented `--donor` key could produce an empty report instead of a hard failure, which weakens operator trust and can hide a broken refresh invocation.
- Mitigation: `scripts/brainstack_refresh_donors.py` now validates selected donor keys and exits with code `2` on unknown keys.
- Status: fixed

### 2. Registry adapter paths were not explicitly constrained to the repo root
- Risk: A corrupted or accidentally bad registry entry could point outside the repo tree and still be treated as a local adapter path candidate.
- Mitigation: the refresh script now resolves adapter paths and rejects any entry that escapes `REPO_ROOT`.
- Status: fixed

### 3. Refresh workflow honesty remains bounded and explicit
- Risk: The new script could be mistaken for an auto-update mechanism.
- Mitigation: documentation and script output continue to state that the workflow only reports local baselines and smoke verdicts; it does not merge or upgrade upstream donors.
- Status: acceptable

## Verification

- `python -m py_compile scripts/brainstack_refresh_donors.py tests/agent/test_brainstack_refresh_workflow.py`
- `uv run --extra dev python -m pytest tests/agent/test_brainstack_refresh_workflow.py tests/agent/test_brainstack_donor_boundaries.py tests/run_agent/test_brainstack_integration_invariants.py tests/agent/test_memory_plugin_e2e.py -q`
- result: `26 passed`
- `python scripts/brainstack_refresh_donors.py --donor missing-donor --strict`
- result: exits `2` with `error: Unknown donor key(s): missing-donor`

## Threats Open

- `0`

## Residual Risk

- The refresh workflow is intentionally manual-review-first. That is acceptable for this phase because the project explicitly chose a middle-ground modularity path instead of a full automatic upstream update system.

