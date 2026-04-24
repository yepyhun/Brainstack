# Phase 10 Donor Boundary Matrix

This phase does not turn donors into live peer runtimes. The goal is to make the donor-shaped substrate explicit, locally owned, and refreshable without creating a fake auto-update story.

| Donor key | Upstream reference | Brainstack-owned runtime path | Local adapter seam | What remains local | What is explicitly not allowed |
| --- | --- | --- | --- | --- | --- |
| `continuity` | `hindsight + hermes-lcm transcript pattern` | `BrainstackMemoryProvider.sync_turn`, `on_pre_compress`, `on_session_end` | `plugins/memory/brainstack/donors/continuity_adapter.py` | session ownership, continuity shelf writes, transcript shelf writes, compression hint generation | no second transcript engine, no peer runtime, no hidden direct transcript writes outside the adapter path |
| `graph_truth` | `graphiti` | `BrainstackMemoryProvider.sync_turn`, `on_session_end` | `plugins/memory/brainstack/donors/graph_adapter.py` | Brainstack graph store schema, local truth retrieval, host ownership | no separate graphiti service in the live Hermes path, no bypass path from provider directly into graph ingestion helpers |
| `corpus` | `mempalace` | `BrainstackMemoryProvider.ingest_corpus_document` | `plugins/memory/brainstack/donors/corpus_adapter.py` | corpus shelf schema, bounded packing, host-facing provider contract | no claim of auto-sync with upstream mempalace, no direct sectioning logic spread back into unrelated provider methods |

## Anti-half-wire invariants

- The live provider path must go through the adapter functions, not only import them.
- The adapter files must be physically distinct from the provider orchestration file so donor-shaped code is easy to audit and refresh.
- The host still sees one Brainstack provider, not donor-branded subproviders.
- The donor registry is descriptive and testable; it must not create a new live tool surface or a second runtime.

## Proof targets

- `tests/agent/test_brainstack_donor_boundaries.py`
- `tests/run_agent/test_brainstack_integration_invariants.py`
- `scripts/brainstack_refresh_donors.py --run-smoke --strict`

