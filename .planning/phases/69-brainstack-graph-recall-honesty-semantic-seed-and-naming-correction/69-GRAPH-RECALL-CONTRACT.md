# Phase 69 Graph Recall Contract

## Authority Boundary

Brainstack owns graph evidence storage, derived semantic evidence indexing, and truthful diagnostic reporting.

Brainstack does not become a graph reasoning governor, scheduler, executor, approval engine, or Graphiti-style ontology engine in this phase.

## Recall Modes

Graph storage health and graph recall mode are separate facts.

- `unavailable`: no current graph rows are available for recall.
- `lexical_seeded`: current graph rows exist, but no current typed semantic graph seed is available.
- `semantic_seeded`: a query selected typed semantic graph evidence without lexical graph rows.
- `hybrid_seeded`: both lexical graph rows and typed semantic graph seeds are active and traceable.

Active storage must never be reported as semantic graph recall by itself.

## Seed Source Rule

Semantic graph seeds may only come from Phase 67 `semantic_evidence_index` rows with:

- `shelf = "graph"`
- active row status
- current semantic evidence fingerprint
- current semantic evidence index version
- source evidence that resolves back to authoritative Brainstack graph state/relation rows

No graph-side keyword farm, alias phrase table, locale dictionary, or hidden donor ontology is allowed.

## Inspectability

Doctor output must expose graph storage and graph recall separately.

Query inspect output must expose a `graph_recall` channel with the applied recall mode in the reason string.

Selected semantic graph evidence must remain typed Brainstack evidence, not answer-text-only context stuffing.

