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

## Source of truth

The canonical inventory lives in:

- [install_into_hermes.py](../scripts/install_into_hermes.py)

The installer now exposes a structured inventory and writes it into:

- `.brainstack-install-manifest.json`

under:

- `host_patch_inventory`

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

Current high-risk host-owned seams include:

- cron scheduler delivery/runtime integration
- credential-pool runtime auth safety for provider-backed cron execution
- memory-provider/write-origin bridge wiring
- gateway lifecycle hooks

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
- Treat Hermes upgrades as unsafe until the inventory targets have been checked.
