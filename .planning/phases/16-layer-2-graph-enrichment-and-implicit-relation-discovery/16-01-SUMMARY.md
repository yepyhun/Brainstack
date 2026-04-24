# Phase 16 Summary

## Outcome

Phase 16 strengthened Brainstack Layer 2 without adding a second memory engine, a new tool surface, or more lexical heuristics.

The phase stayed bounded:

- explicit truth remains the primary graph path
- historical truth stays tied to the existing temporal state model
- inferred links are now a separate, low-priority graph class instead of being flattened into explicit truth
- graph recall is packaged in clearer sections instead of one mixed blob

## Source Changes

- extended the L2 store in `brainstack/db.py`
  - added `graph_inferred_relations`
  - added explicit-vs-inferred shadowing rules
  - improved `search_graph()` ranking with truth-class priority, overlap, confidence, and bounded telemetry adjustment
- extended Tier-2 extraction in `brainstack/tier2_extractor.py`
  - optional bounded `inferred_relations` output
  - conservative prompt guidance for inferred links
- extended reconciliation in `brainstack/reconciler.py`
  - inferred relations now reconcile through their own store path
- updated graph recall packaging in `brainstack/retrieval.py`
  - `### Current Truth`
  - `### Open Conflicts`
  - `### Historical Truth`
  - `### Inferred Links`
- updated graph usefulness weighting in `brainstack/usefulness.py`
  - inferred links are intentionally ranked below explicit truth
- added or updated coverage in:
  - `tests/test_brainstack_real_world_flows.py`
  - `tests/test_brainstack_retrieval_contract.py`

## Validation

### Source-side validation

- targeted Phase 16 regression slice passed:
  - `28 passed`
  - executed against the local Brainstack source with Hermes runtime dependencies available
- covered behaviors:
  - inferred relation normalization
  - inferred relation reconciliation
  - explicit truth outranking inferred links
  - explicit relation shadowing of matching inferred relations
  - graph recall packaging with separated truth classes

### Live runtime validation

- installer + doctor passed on the Bestie target after carry-through
- Docker rebuild completed and the live runtime returned to:
  - `running; connected=discord`
- live container proof passed:
  - `has_inferred_table_code=True`
  - `has_inferred_relation_label=True`
  - `has_tier2_inferred_schema=True`
  - `explicit_before_inferred=True`
  - `block_has_current_truth=True`
  - `block_has_inferred_links=True`
  - `block_has_inferred_relation=True`

## Result

Brainstack L2 is now materially stronger than the old lexical row-priority path:

- explicit current truth stays first-class
- history stays visible when needed
- inferred links exist but are bounded and clearly labeled
- conflicts remain explicit
- recall packaging is easier for the model to use silently

This is still Brainstack-owned L2, not a Mnemosyne transplant and not a benchmark-driven rewrite.

## Follow-up

Next step is Phase `16` verify-work.
