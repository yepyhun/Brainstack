# Supported Environments

This document defines Brainstack GA support scope. It prevents universal bug-free claims.

## Supported GA Scope

- Source of truth: `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`.
- Installer path: Brainstack wizard / `scripts/install_into_hermes.py`.
- Hermes target: latest Hermes checkout with `.brainstack-install-manifest.json`.
- Runtime: Docker image built from the installed Hermes checkout.
- Platform proof: synthetic Gateway E2E plus live Discord bot smoke.
- Memory backend: configured Brainstack SQLite/Kuzu/Chroma paths created by installer.
- Tool runtime: Hermes capability manifest, ToolLoader/deferred schema, terminal/file/web only when configured available.
- Approval runtime: side-effect tool execution blocked without approval permit.
- Workspace: clean Docker workspace and explicit mounted project workspace when file tests need fixture files.
- Provider matrix: default configured provider plus targeted stronger-model slice only for high-value reasoning/style/tool-use probes.

## Unsupported / Non-GA Scope

- Arbitrary host filesystem without explicit mount contract.
- User-token/selfbot Discord behavior.
- Missing web/browser backend while expecting successful browsing.
- Every provider/model combination in the market.
- Unlimited long-running autonomous workflow correctness.
- Manual Discord prompt transcript as sole proof.
- Docker-only, mirror-only, or installed-Hermes-only fixes not present in source of truth.

## Proof Chain

GA proof must flow:

```text
source of truth -> wizard install -> latest Hermes checkout -> Docker image -> synthetic Gateway E2E -> failure bundle gate -> live Discord smoke
```

If any link is missing, GA READY is blocked.
