# Brainstack Host Patch Surface

This document exists for one reason: when Hermes moves quickly, Brainstack host integration must stay auditable.

## What counts as a host patch

Brainstack has three different install surfaces:

1. Plugin payload copy
   - `brainstack/` copied into `plugins/memory/brainstack/`
   - This is the normal source-of-truth payload.

2. Runtime config mutation
   - Agent config updates such as provider selection and auxiliary task wiring.
   - This is runtime ownership, not copied plugin code.

3. Host file patching
   - Explicit installer modifications to Hermes host files.
   - This is the risky surface that needs tracking across upstream Hermes versions.

4. Gateway patch bundle
   - `patches/hermes_gateway/*.patch` applied by the installer when upstream Hermes lacks the required Gateway/runtime contracts.
   - This is source-of-truth for pending Hermes patches such as TurnContract, deterministic renderer, and capability-preserving deferred tool schema loading.

## Source of truth

The canonical inventory lives in:

- [install_into_hermes.py](../scripts/install_into_hermes.py)

The installer now exposes a structured inventory and writes it into:

- `.brainstack-install-manifest.json`

under:

- `host_patch_inventory`

Gateway patch bundle status is written under:

- `hermes_gateway_patches`

## How to inspect the patch surface

Print the current source-runtime inventory:

```bash
python scripts/brainstack_patch_inventory.py --runtime source --format markdown
```

Print the Docker inventory:

```bash
python scripts/brainstack_patch_inventory.py --runtime docker --format markdown
```

Print machine-readable JSON:

```bash
python scripts/brainstack_patch_inventory.py --runtime docker --format json
```

## Reading the inventory

Each host patch entry records:

- `target`: which Hermes file is modified
- `patcher`: which installer function owns that patch
- `scope`: what seam category it belongs to
- `purpose`: what the patch does
- `why`: why Brainstack still owns that seam today
- `category`: whether it is a required Brainstack seam, hygiene patch, compatibility
  hotfix, or temporary upstream Hermes bugfix
- `removal_condition`: the concrete upstream state where the installer should stop
  applying it

## Temporary Upstream Hermes Hotfixes

Temporary upstream hotfixes are not Brainstack product features. They are
small, isolated Hermes runtime workarounds that keep the live Brainstack install
usable while an upstream Hermes issue is open.

Rules for this category:

- every entry must link to the upstream Hermes issue/PR in `removal_condition`
  when an upstream tracker exists
- the patcher must skip itself when upstream already has an equivalent fix
- the patch must be listed in `HOST_PATCH_INVENTORY`
- the installer manifest must keep it visible under `host_patch_inventory`
- remove it as soon as upstream Hermes owns the behavior

Current high-risk host-owned seams include:

- cron scheduler delivery/runtime integration
- credential-pool runtime auth safety for provider-backed cron execution
- memory-provider/write-origin bridge wiring
- gateway lifecycle hooks
- Hermes capability preservation while deferring JSON tool schemas

### Hermes Cron Authority Hotfix

Brainstack may temporarily patch Hermes cron authority while upstream does not
ship a native `HERMES_CRON_HOME` resolver.

The intended behavior is narrow:

- ordinary profiles keep profile-local cron under their own `HERMES_HOME`
- coordinated worker systems may explicitly set `HERMES_CRON_HOME` to share one
  cron authority
- `jobs.json`, `cron/output`, scheduler `.tick.lock`, and spawned profile
  workers must all use the same explicit authority when it is set
- the wizard must skip this patch once Hermes already implements equivalent
  behavior

This hotfix is not Brainstack cron ownership. Brainstack only installs and
diagnoses the temporary Hermes seam so memory/proactive status does not report
healthy work while profile workers are looking at a different scheduled-job
store.

### Hermes OpenAI Runtime Credential-Pool Hotfix

Brainstack may temporarily patch Hermes OpenAI-family runtime auth while upstream
reports credential-pool logins as valid in `hermes auth status` but runtime
provider resolution still only reads legacy provider state.

The intended behavior is narrow:

- `hermes auth status openai-codex` and runtime execution must agree
- credential-pool OAuth entries may be used by cron/worker runtime resolution
- legacy provider-state auth remains supported
- the wizard must skip this patch once Hermes natively resolves runtime
  credentials from the same pool used by auth status

This hotfix is not a Brainstack auth system. It only prevents scheduled or
worker runs from failing as logged out while Hermes itself reports a valid
login.

This is the minimum required to answer these questions quickly:

- What did Brainstack touch in this checkout?
- Is this patch Brainstack-owned or just runtime config?
- Which seams still need to move upstream into Hermes?
- Did a new Hermes release break one of our known patch targets?

## Intended use during Hermes upgrades

When a new Hermes version lands:

1. Print the inventory.
2. Compare each `target` against the new upstream file.
3. Decide per item:
   - keep as-is
   - adapt to upstream changes
   - remove because Hermes now owns the seam
4. Update the installer inventory before declaring the upgrade safe.

## Anti-goals

- Do not treat copied plugin payload files as host patches.
- Do not mix runtime config drift with source patch drift.
- Do not add silent host mutations without adding them to the installer inventory.
- Do not shrink configured Hermes capabilities to reduce tokens; defer schema loading instead.
- Treat Hermes upgrades as unsafe until the inventory targets have been checked.
