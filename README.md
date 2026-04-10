# Brainstack

Brainstack is a Hermes-native composite memory provider and local memory substrate.

It currently runs **inside Hermes-Agent as a direct `MemoryProvider` plugin**, not as a standalone API-first memory server. The local store is separated so tightly scoped sidecars can share the same SQLite state, but runtime memory ownership stays with Brainstack.

## Core inspiration

Brainstack is primarily built from three donor lines:

1. **[Hindsight](https://github.com/vectorize-io/hindsight)** - For temporal state preservation, bounded history, and preserving old states rather than destructively overwriting past knowledge.
2. **[Graphiti](https://github.com/getzep/graphiti)** - For explicitly surfacing graph conflicts, tracking entity relationships, and managing temporal truths natively.
3. **[MemPalace](https://github.com/yepyhun/MemPalace)** - For modular, high-performance retrieval and FTS/Semantic FUSION handling of large corpuses without massive token overhead.

This translates into a strict internal separation of concerns:

| Layer | Inspiration | Core Responsibility |
| :--- | :--- | :--- |
| **L1** | **Hindsight** | recency, session continuity, after-turn learning |
| **L2** | **Graphiti** | entity-relation-temporal graph, current/previous truth |
| **L3** | **MemPalace** | big corpus, FUSION context packing |

Additional patterns also influence the current code:

- **Hermes-LCM transcript pattern** for bounded raw transcript retention and temporal evidence fallback
- **RTK-style sidecar discipline** for token-aware auxiliary work without taking memory ownership

## Current runtime architecture

Brainstack currently routes memory into five shelves instead of a flat memory blob:

1. **Profile shelf**  
   Durable identity, preference, and shared-work anchors.
2. **Continuity shelf**  
   Session carry-over, compression snapshots, and pending work state.
3. **Transcript shelf**  
   Append-only raw turns used only as bounded evidence, not as a second live memory engine.
4. **Graph-truth shelf**  
   Entities, relations, temporal state, supersession, and explicit conflict surfacing.
5. **Corpus shelf**  
   External documents, sectioning, bounded recall, and large-corpus packing.

On top of the shelves, Brainstack uses a **risk-aware control plane**:

- high-stakes questions suppress memory-only bluffing
- preference-style questions prefer compact profile recall
- temporal/explanatory questions expand continuity and graph evidence
- transcript recall is bounded and session-scoped

## What is true in the current codebase

- Brainstack is intended to be the **single live memory path** when Hermes builtin memory is disabled.
- The donor-inspired parts are behind **explicit local adapters**:
  - `brainstack/donors/continuity_adapter.py`
  - `brainstack/donors/graph_adapter.py`
  - `brainstack/donors/corpus_adapter.py`
- Donor baselines are tracked via a **bounded refresh workflow**, not hidden copy-paste drift.
- The refresh script can report local adapter state and optionally run local smoke checks.
- The current Brainstack baseline is **SQLite/FTS based** and does **not** require TEI/Jina or any external embedding service.

## What this repo is not claiming

- It is **not** a standalone API-first memory product yet.
- It is **not** a one-click upstream auto-update system.
- It is **not** the full Hermes repository.
- It does **not** claim automatic donor compatibility without review.

## Repo scope

This repository is a focused Brainstack slice containing:

- the Hermes-native Brainstack plugin code under [`brainstack/`](./brainstack)
- donor boundary and refresh logic under [`brainstack/donors/`](./brainstack/donors) and [`scripts/`](./scripts)
- focused test slices under [`tests/`](./tests)
- optional RTK sidecar integration surface in [`rtk_sidecar.py`](./rtk_sidecar.py)

## Repo layout

```text
brainstack/
  __init__.py
  control_plane.py
  db.py
  transcript.py
  graph.py
  corpus.py
  retrieval.py
  donors/
scripts/
  brainstack_refresh_donors.py
tests/
rtk_sidecar.py
```

## Running expectations

This repository reflects a **Hermes-integrated** Brainstack slice. Some modules and tests still depend on Hermes runtime interfaces such as `agent.memory_provider` and Hermes home/config conventions.

So the correct framing is:

- **native Hermes integration first**
- **shared local store second**
- **standalone API later, only if intentionally built**

## Update model

Current updateability is the middle path:

- explicit donor registry
- explicit local adapter seams
- bounded refresh reporting
- local smoke verification

This is much cleaner than baked-in donor drift, but it is still **not** full automatic upstream syncing.
