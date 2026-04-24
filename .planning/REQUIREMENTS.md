# Requirements: Hermes Brainstack v2.1

**Defined:** 2026-04-10
**Core Value:** Make Hermes feel materially smarter through safer, stronger long-term memory without breaking the single-provider contract or token discipline.

## v2.1 Requirements

### Profile Extraction Pipeline

- [ ] **PROF-01**: Explicit self-statements and direct preferences still route through a fast Tier-1 extractor.
- [ ] **PROF-02**: Implicit user preferences can be inferred from natural conversation through a separate Tier-2 path.
- [ ] **PROF-03**: Tier-1 and Tier-2 profile extraction use explicit Brainstack-owned seams rather than ad hoc provider logic.

### Preference Safety

- [ ] **SAFE-01**: Low-confidence Tier-2 inferences do not silently become durable profile facts.
- [ ] **SAFE-02**: A later user correction can demote or supersede a previously inferred preference cleanly.
- [ ] **SAFE-03**: Old and new preference states remain temporally visible instead of destructive overwrite.

### Recall Quality

- [ ] **RECALL-01**: Stored preferences improve everyday agent continuity and reduce repeated user explanations.
- [ ] **RECALL-02**: Important or uncertain recalled preferences can surface their basis without spamming provenance on every turn.
- [ ] **RECALL-03**: Profile recall stays bounded so the new inference layer does not blow up token usage.

### Host And Modularity

- [ ] **HOST-01**: Hermes still sees one Brainstack provider and no second memory runtime.
- [ ] **HOST-02**: The Tier-2 inference capability can be upgraded or swapped without breaking the Hermes-facing provider contract.
- [ ] **HOST-03**: The new profile-intelligence pipeline does not bypass the donor-boundary and anti-half-wire standards established in v2.0.

## Deferred / Later

### Future Work

- **AUTO-01**: Full one-click donor auto-update architecture
- **AUTO-02**: API-first standalone Brainstack runtime
- **AUTO-03**: Large-scale corpus/graph re-ranking overhaul beyond the profile milestone

## Out of Scope

| Feature | Reason |
|---------|--------|
| Full donor auto-update automation | Too infrastructure-heavy for the next highest-leverage milestone |
| New peer memory runtime or standalone service | Conflicts with the current one-provider host architecture |
| Benchmark-specific preference heuristics | Would repeat the old baked-in / fake-smart failure mode |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PROF-01 | Phase 11 | Pending |
| PROF-02 | Phase 12 | Pending |
| PROF-03 | Phase 11 | Pending |
| SAFE-01 | Phase 13 | Pending |
| SAFE-02 | Phase 13 | Pending |
| SAFE-03 | Phase 13 | Pending |
| RECALL-01 | Phase 14 | Pending |
| RECALL-02 | Phase 13 | Pending |
| RECALL-03 | Phase 13 | Pending |
| HOST-01 | Phase 11 | Pending |
| HOST-02 | Phase 12 | Pending |
| HOST-03 | Phase 11 | Pending |

**Coverage:**
- v2.1 requirements: 12 total
- mapped to phases: 12
- unmapped: 0

---
*Requirements defined: 2026-04-10*
*Last updated: 2026-04-10 after v2.1 milestone definition*
