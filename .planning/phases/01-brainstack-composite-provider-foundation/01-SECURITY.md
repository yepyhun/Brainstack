---
phase: 01
slug: brainstack-composite-provider-foundation
status: verified
threats_open: 0
asvs_level: 1
created: 2026-04-10
---

# Phase 01 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

This phase did not ship runtime Brainstack code yet. The security review is therefore architecture-focused and derived from the Phase 1 plan, implementation contract, and summary artifacts.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Hermes host -> Brainstack provider seam | The only allowed external memory-provider boundary exposed to Hermes | memory hook calls, recall blocks, provider lifecycle signals |
| Brainstack control plane -> owned memory layers | Policy layer coordinates continuity, graph truth, corpus, and profile owners | retrieval decisions, packing rules, confidence/provenance policy |
| Brainstack core -> sidecars/shells | RTK and My-Brain-Is-Full-Crew may influence efficiency or workflow, but not canonical ownership | filtered outputs, workflow entrypoints, bounded orchestration hints |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-01-01 | Tampering / Integrity | Memory ownership boundaries | mitigate | Freeze ownership map, architecture invariants, and extension-slot rules so no sidecar or donor can silently become a second canonical owner | closed |
| T-01-02 | Information exposure / Overreach | Provider tool surface | mitigate | Keep Brainstack model-facing tools disabled by default in Phase 1; use hooks first and require explicit escalation for any future tool | closed |
| T-01-03 | Residual legacy-path exposure | Built-in Hermes memory live path | accept | Displacement is explicitly scoped and deferred to the dedicated implementation phase; until then the risk is tracked as a temporary accepted risk rather than being hidden | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01-01 | T-01-03 | Phase 1 is an architecture-foundation phase, not the runtime displacement phase. The residual built-in memory live-path risk is intentionally deferred to the later displacement implementation work rather than falsely treated as already removed. | Codex + user-approved Phase 1 scope | 2026-04-10 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-10 | 3 | 3 | 0 | Codex (`/gsd-secure-phase 1`) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-04-10
