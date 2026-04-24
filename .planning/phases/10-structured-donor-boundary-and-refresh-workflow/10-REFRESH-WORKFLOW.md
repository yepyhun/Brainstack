# Phase 10 Refresh Workflow

Phase 10 is a middle-path modularity refactor. It improves refreshability, but it does **not** promise one-click donor auto-update.

## What the refresh entrypoint does

- reports the tracked donor registry and local adapter boundaries
- verifies the local adapter files exist
- can run the declared local compatibility smoke tests
- returns an honest pass/fail result for the current local boundary

Entrypoint:

```bash
python scripts/brainstack_refresh_donors.py
python scripts/brainstack_refresh_donors.py --run-smoke --strict
python scripts/brainstack_refresh_donors.py --donor corpus --run-smoke --strict
```

## What it does not do

- it does not clone, merge, or overwrite upstream donor projects
- it does not claim that upstream compatibility is guaranteed without review
- it does not spin up donor runtimes inside Hermes
- it does not create a second memory engine beside Brainstack

## Honest donor refresh process

1. Pick one donor boundary to review.
2. Check the upstream release, commit, or design delta manually.
3. Decide whether the delta belongs:
   - only in the local adapter seam
   - in the local Brainstack-owned substrate
   - or nowhere because it would break the single-provider contract
4. Apply the local code change.
5. Run:
   - `python scripts/brainstack_refresh_donors.py --donor <key> --run-smoke --strict`
6. Only declare the donor refreshed if the local smoke stays green and the single Brainstack runtime path is still intact.

## Why this middle path is acceptable

- it removes scattered donor-shaped logic from the provider core
- it makes future refresh work obvious instead of hidden
- it avoids fake one-click update claims
- it keeps the host integration simple and single-owner

