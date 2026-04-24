# Phase 58 Half-Wired Surface Audit

## Reviewed surfaces

### `host_payload/agent/brainstack_mode.py`

Decision:

- keep as bounded compatibility shim

Reason:

- older Hermes checkouts may still import these names
- the file is already reduced to no-op return values
- it no longer performs Brainstack-only tool gating, personal-memory governance, or reply enforcement

### installer canonicalization regexes in `scripts/install_into_hermes.py`

Decision:

- keep as migration-only helpers

Reason:

- they are not active runtime intelligence
- they only canonicalize old degraded `USER.md` entries into the explicit native-truth form
- they are donor-safe and bounded to install/canonicalization time

### `brainstack/behavior_policy.py`

Decision:

- keep with explicit reason

Reason:

- it is still referenced by shipped runtime code
- deleting it would be unsafe without a broader runtime-entry refactor
- explicit native rule packs are no longer stored in this authority lane after the Phase 56/58 demotion path

## Personal/dev noise audit

Shipped source grep checked for:

- `Tomi`
- `Bestie`
- `LauraTom`
- `brainstack logok`

Result:

- no matches in shipped source surfaces reviewed for this phase

## Remaining accepted complexity

The following hotspots remain large, but Phase 58 did not widen them further:

- `brainstack/__init__.py::prefetch`
- `brainstack/db.py::_init_schema`
- `brainstack/db.py::upsert_behavior_contract`
- `scripts/install_into_hermes.py::_patch_gateway_run`
- `scripts/install_into_hermes.py::_patch_cron_scheduler`
- `scripts/brainstack_doctor.py::_check_config`

Interpretation:

- these are maintainability debt, not immediate correctness blockers after the Phase 58 cleanup
- they remain valid candidates for later stabilization-only work
