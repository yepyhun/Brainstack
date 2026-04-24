---
phase: 09
slug: hindsight-lossless-transcript-hardening
status: verified
threats_open: 0
asvs_level: 1
created: 2026-04-10
---

# Phase 09 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

This phase shipped runtime Brainstack transcript hardening, so the security review is focused on raw-turn retention, bounded prompt recall, session isolation, and preservation of single-owner memory behavior inside Hermes.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Hermes host -> Brainstack provider | The host asks one composite provider for recall and sync behavior | user turns, assistant turns, prefetch blocks, lifecycle hooks |
| Brainstack control plane -> transcript shelf | Policy decides whether raw transcript evidence may be surfaced | transcript search queries, bounded transcript rows, policy flags |
| Brainstack transcript shelf -> prompt assembly | Only packed transcript snippets may cross into the working-memory block | bounded evidence lines, provenance tags, same-session markers |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-09-01 | Information exposure | Transcript retrieval scope | mitigate | Restrict transcript search to the current session instead of ranking other sessions lower; verify with explicit session-isolation test coverage | closed |
| T-09-02 | Prompt overreach / Noise | Transcript prompt packing | mitigate | Keep transcript promotion as bounded fallback evidence only, with explicit `transcript_limit` and `transcript_char_budget` enforcement plus regression coverage | closed |
| T-09-03 | Ownership regression | Host memory path | mitigate | Preserve one effective memory owner by keeping transcript hardening inside Brainstack seams and verifying no second context-engine or live memory tool path appears | closed |
| T-09-04 | Classification miss | High-stakes query suppression | accept | High-stakes transcript suppression currently depends on bounded lexical term detection in the control plane; this is acceptable at this phase because transcript recall is already fallback-only, bounded, and now session-local, but later semantic policy hardening may still improve it | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-09-01 | T-09-04 | The current high-stakes suppressor uses lexical heuristics rather than a stronger semantic risk classifier. Because transcript recall is bounded, fallback-only, and session-local after this audit, the residual risk is acceptable for now and should be revisited only if later real-world usage shows misses. | Codex + current Phase 09 scope | 2026-04-10 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-10 | 4 | 4 | 0 | Codex (`/gsd-secure-phase 09`) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-04-10
