# Phase 18 Summary

## Outcome

Phase 18 moved Layer 2 off the old SQLite-only graph read path and established the first real second storage motor in the recovery architecture.

The new shape is now explicit:

- SQLite remains the shell-side canonical mirror and publish source
- `Kuzu` is now the active embedded graph backend target for Layer 2 reads
- graph publication now flows through a store-agnostic publish journal instead of ad hoc direct writes
- Layer 1 stayed stable; the richer graph channel comes through the existing executive retrieval contract instead of another L1 rewrite

This phase stayed within the hard boundaries:

- no L1 redesign hidden inside the graph work
- no L3/Chroma migration smuggled into the phase
- no rebuild dependency during normal source execution
- no regression back to all-SQLite graph reads as the effective center

## Source Changes

- added `brainstack/graph_backend.py`
  - store-agnostic graph backend protocol
  - backend factory for `sqlite` / `kuzu` switching
- added `brainstack/graph_backend_kuzu.py`
  - embedded `Kuzu` graph backend
  - schema creation for entities, states, conflicts, explicit relations, and inferred relations
  - SQLite snapshot publication into Kuzu
  - richer graph search with:
    - explicit + inferred edges
    - bidirectional neighbor expansion
    - punctuation-tolerant query tokenization
    - inflected-token matching that still finds canonical entity names
- rewired `brainstack/db.py`
  - provider/store config now accepts `graph_backend` and `graph_db_path`
  - added store-agnostic `publish_journal`
  - added empty-backend bootstrap from existing SQLite graph data
  - public graph writes now publish entity-subgraph snapshots to the active backend
  - graph reads now prefer the configured backend while keeping existing fact-class sorting
- updated `brainstack/__init__.py`
  - default graph backend target is now `kuzu`
  - default graph DB path is `$HERMES_HOME/brainstack/brainstack.kuzu`
- updated installer and doctor:
  - `scripts/install_into_hermes.py`
  - `scripts/brainstack_doctor.py`
  - installer now writes `graph_backend` + `graph_db_path` defaults
  - doctor now requires the new backend files and checks `kuzu` availability
- updated `README.md`
  - repo layout now includes the backend files
  - installer behavior now documents the `Kuzu` graph config defaults
- added focused Phase 18 coverage:
  - `tests/test_brainstack_graph_backend_kuzu.py`

## Validation

### Source-side validation

- syntax compile passes for the touched source and tooling files
- targeted Phase 18 source suite passes:
  - `26 passed in 1.45s`
- covered behaviors now include:
  - SQLite → Kuzu bootstrap
  - published journal rows for the Kuzu target
  - failure then successful replay in the publish journal
  - inflected / punctuated query handling in the Kuzu graph search
  - preserved current-vs-prior truth and inferred-link packaging through the existing L1 contract

### Installer / runtime carry-through

- source-side installer and doctor were updated for the new graph backend
- live carry-through into the Bestie checkout is currently blocked by target file permissions:
  - `hermes-config/bestie/config.yaml` is root-owned and unreadable from the current user
- because of that:
  - installer dry-run fails closed on the target checkout
  - real install also fails closed on the same permission boundary
- no rebuild was attempted
- no push was performed

## Result

Phase 18 materially improves the donor-first recovery path:

- Layer 2 now has a real embedded graph backend target instead of staying trapped in the SQLite mirror
- the shell now owns the first real cross-store publish contract through the journal
- graph usefulness improves without rewriting Layer 1
- the future Phase 19 extension point is cleaner because the journal core is already store-agnostic rather than Kuzu-hardcoded

This does **not** mean the full donor-strength graph restoration is finished. The remaining gap is the broader Graphiti-shaped usefulness and live runtime carry-through once the target checkout permissions are fixed.

## Follow-up

- Phase 18 verify should focus on practical graph usefulness, not on architecture restatement
- the blocked Bestie install path should only be retried after the target config permission issue is fixed
- Phase 19 can now extend the same publish journal to `Chroma` instead of inventing a second coordination mechanism
