# Phase 76 Corpus Ingest Contract

## Decision

Brainstack corpus ingest is a typed source-adapter pipeline, not raw prompt stuffing.

Every corpus source must normalize into:

- source adapter id
- source id
- stable key
- title
- document kind
- source URI
- bounded sections
- document hash
- section hashes
- citation ids
- principal scope and provenance metadata
- corpus ingest fingerprint

## Fingerprint Rule

The corpus fingerprint covers:

- schema version
- source adapter contract version
- normalizer version
- sectioner version
- embedder/index version
- source adapter
- document hash

If those versions or hashes drift, corpus ingest status must report degraded/stale state instead of silently pretending the index is fresh.

## Re-Ingest Rule

Re-ingesting the same stable source with the same normalized document hash is `unchanged`.

Re-ingesting the same stable source with changed content is `updated` and replaces sections/FTS rows without creating duplicate documents.

## Citation Rule

Every selected corpus section must expose a citation id and section hash. Rendered corpus recall includes citation ids in labels.

## Non-Goals

- No raw wiki/file dumping.
- No uncontrolled file stuffing.
- No bypass around corpus budgets.
- No new source-of-truth owner outside Brainstack corpus records.
- No language-specific corpus hacks.

