# Phase 75 Associative Expansion Contract

## Decision

Brainstack may perform bounded associative expansion from already retrieved graph evidence. The expansion is a retrieval/ranking aid, not a new authority layer.

The first implementation is graph-only:

- seed rows come from lexical graph rows and typed semantic graph seeds;
- anchors are extracted from graph entity fields, not from locale-specific cue lists;
- every run has max seed, depth, candidate, search, and shelf bounds;
- every accepted or suppressed candidate is traceable.

## Bounds

Default Phase 75 bounds:

- max seed count: 4
- max depth: 1
- max candidate count: bounded by graph packet limits, capped at 8
- max search count: 12
- allowed shelves: `graph`

## Inclusion Rule

Associative candidates may enter the graph shelf only as low-weight retrieval candidates. They do not override profile, operating, task, or current authoritative truth.

An expanded graph candidate must carry at least one query concept in its own graph text or typed metadata. A relation alone is not enough to include unrelated connected state.

## Trace Rule

Inspect output must expose:

- seed rows
- anchors
- hop depth
- candidate counts
- included candidates
- suppressed candidates with reasons
- run cost

## Non-Goals

- No unbounded spreading activation.
- No language-specific phrase farms.
- No hidden rerank farm.
- No authority-blind semantic volume.
- No scheduler, executor, approval, or runtime governance behavior.

