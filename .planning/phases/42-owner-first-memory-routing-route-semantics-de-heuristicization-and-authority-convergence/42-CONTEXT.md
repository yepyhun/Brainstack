# Phase 42 Context

## problem statement

After Phase 41, the product still has residual routing and authority debt:

- `control_plane.py` still uses query-shape analysis such as `high_stakes`, `profile_slot_targets`, `operating_like`, and `task_like`
- `executive_retrieval.py` still contains cue families and route fallback behavior that can change surfaced mode
- `retrieval.py` still exposes a multi-authority system where exact archival recall, ordinary-turn lane, and fallback shelves can diverge

This is no longer the old broken state, but it is still not masterpiece-grade or strict-inspector clean.

## why this phase exists

- the product cannot honestly claim fully converged memory truth while exact recall, ordinary-turn guidance, and route fallback can still surface different authorities
- this is the first corrective phase after the audit because every later proof surface depends on routing truth being stable

## findings this phase is intended to close

- Phase 41 Batch 2:
  - 4. Control-plane routing is still not fully owner-first
  - 5. Executive route selection still depends on cue tables and route fallback
  - 6. Retrieval still exposes multi-authority fallback semantics
- Phase 41 Batch 5:
  - 14. Proof surface debt on the most important routing/orchestration hubs

## architectural posture

- do not build “better heuristics”
- do not widen cue tables
- do not reintroduce prompt tricks to hide authority divergence
- do not paraphrase the immutable principles; reference them directly

## success shape

- route selection grounded in owner-derived signals and deterministic authority state
- exact recall and ordinary-turn lane tied to one authority lineage
- fallback remains explicit and inspectable, not silent
- proof surface can show which authority generation the user actually saw

## canonical principle reference

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`

## recommended model level

- `xhigh`
