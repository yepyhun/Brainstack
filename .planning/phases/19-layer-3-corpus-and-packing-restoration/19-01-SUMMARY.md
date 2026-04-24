# Phase 19 Summary

## Outcome

Phase 19 moved Layer 3 off the old SQLite-only corpus center and established the first real embedded semantic corpus backend in the recovery architecture.

The new shape is now explicit:

- SQLite remains the shell-side canonical corpus snapshot and lexical fallback store
- `Chroma` is now the active embedded semantic corpus backend target for Layer 3 reads
- corpus publication now flows through the same store-agnostic publish journal core instead of ad hoc direct backend writes
- Layer 1 stayed stable; the semantic corpus leg came alive through the existing executive retrieval contract instead of another L1 redesign

This phase stayed within the hard boundaries:

- no L1 conceptual rewrite hidden inside corpus work
- no L2 redesign smuggled into the phase
- no rebuild dependency during normal source execution
- no regression back to all-SQLite corpus retrieval as the effective center

## Source Changes

- added `brainstack/corpus_backend.py`
  - store-agnostic corpus backend protocol
  - backend factory for `sqlite` / `chroma` switching
- added `brainstack/corpus_backend_chroma.py`
  - embedded `Chroma` corpus backend
  - lazy import boundary
  - telemetry-disabled client settings
  - semantic section retrieval with stable metadata shaping
- rewired `brainstack/db.py`
  - provider/store config now accepts `corpus_backend` and `corpus_db_path`
  - added empty-backend bootstrap from existing SQLite corpus data
  - added resumable replay for pending/failed corpus publications
  - corpus writes now publish document snapshots to the active backend target
  - corpus reads now expose:
    - lexical fallback via SQLite
    - semantic retrieval via the configured corpus backend
    - explicit semantic channel status derived from backend presence/health
  - added corpus retrieval telemetry updates on `corpus_sections.metadata_json`
- updated `brainstack/executive_retrieval.py`
  - semantic channel is no longer hardcoded degraded
  - semantic corpus results now flow through the existing RRF fusion path
  - selected rows now carry fused-channel metadata for downstream use
- updated `brainstack/control_plane.py`
  - corpus retrievals now record telemetry the same way profile/graph retrievals do
- updated `brainstack/retrieval.py`
  - bounded corpus packing now reduces duplicate snippets
  - per-document overrepresentation is capped without rewriting packing into a new engine
- updated `brainstack/__init__.py`
  - config schema now exposes `corpus_backend` and `corpus_db_path`
  - installer-facing defaults target `chroma`
  - runtime fallback remains `sqlite` when corpus backend is not configured
- updated installer and doctor:
  - `scripts/install_into_hermes.py`
  - `scripts/brainstack_doctor.py`
  - installer now writes `corpus_backend` + `corpus_db_path` defaults
  - doctor now requires the new corpus backend files and checks `chromadb` availability
- updated `README.md`
  - runtime architecture now reflects SQLite shell state + Kuzu + Chroma
  - repo layout now includes the corpus backend files
  - installer behavior now documents the `Chroma` corpus config defaults
- added focused Phase 19 coverage:
  - `tests/test_brainstack_corpus_backend_chroma.py`
  - `scripts/run_brainstack_phase19_eval_ladder.py`

## Validation

### Source-side validation

- syntax compile passes for the touched source, tooling, and test files
- bounded Phase 19 eval ladder passes:
  - Gate A: `4 passed`
  - Gate B: `2 passed`
  - Gate C: skipped when `COMET_API_KEY` is absent
- extra targeted regression suite passes:
  - `tests/test_install_into_hermes.py`
  - `tests/test_brainstack_graph_backend_kuzu.py`
  - `7 passed`

### Runtime carry-through

- source-side installer and doctor now know about the `Chroma` backend
- no live Bestie install/rebuild was attempted in this phase
- this follows the current workflow rule that rebuild is only for bounded runtime smoke, not for every execute step
- no push was performed

## Result

Phase 19 materially improves the donor-first recovery path:

- Layer 3 now has a real embedded semantic corpus backend target instead of staying trapped in the SQLite mirror
- the shell now coordinates both graph and corpus publish targets through one store-agnostic journal core
- the L1 semantic corpus leg is genuinely live without changing L1’s contract shape
- corpus packing improved only as a bounded quality layer, not as a fake retrieval rescue

This does **not** mean the full recovery track is finished. The remaining step is the combined proof phase, where the restored layers must show that the assembled system is genuinely stronger end to end than the diluted pre-recovery state.

## Follow-up

- Phase 19 verify should focus on practical corpus usefulness, not backend novelty
- final push should wait until the current recovery track is genuinely complete
- Phase 20 should use the new eval ladders as bounded gates before any heavier final-boss proof
