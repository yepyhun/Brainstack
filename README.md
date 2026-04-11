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

## Installation into Hermes

Brainstack is meant to be installed into a fresh Hermes checkout, not copied around by hand.

Dry-run compatibility check:

```bash
python install_into_hermes.py /path/to/hermes-agent --enable --doctor --dry-run --runtime docker
```

Real install:

```bash
python install_into_hermes.py /path/to/hermes-agent --enable --doctor --runtime docker
```

Local non-Docker install:

```bash
python install_into_hermes.py /path/to/hermes-agent --enable --doctor --runtime local
```

What the installer does:

- copies `brainstack/` into `plugins/memory/brainstack/`
- copies `rtk_sidecar.py` when the target Hermes checkout has `agent/`
- copies Brainstack host helper payload into the target Hermes checkout:
  - `agent/brainstack_mode.py`
- patches recognized Hermes host files so Brainstack can be the single live memory owner:
  - `run_agent.py` strips legacy `memory` and `session_search` tools in Brainstack-only mode
  - `gateway/run.py` routes reset / resume / expiry boundaries through a Brainstack-aware finalizer
  - `gateway/run.py` also keeps platform runtime status truthful during connect, reconnect, and disconnect paths
  - `gateway/status.py` is patched so `None` can clear stale `exit_reason` and platform error fields instead of silently preserving old failure state
  - gateway maintenance agents stop carrying the legacy memory toolset in Brainstack-only mode
- patches recognized Hermes config so:
  - `memory.provider: brainstack`
  - `memory.memory_enabled: false`
  - `memory.user_profile_enabled: false`
- writes a sanitized `.brainstack-install-manifest.json`
- runs doctor checks if requested
- supports both `docker` and `local` runtime modes through the same installer
- in `docker` mode, generates `scripts/hermes-brainstack-start.sh` inside the target Hermes checkout
- in `docker` mode, generates `scripts/hermes-gateway-healthcheck.py` and patches Compose to use readiness-aware health instead of process-only health

What it intentionally does **not** do:

- it does not guess unknown upstream host changes
- it does not inject secrets
- it does not pretend API-first deployment already exists
- it does not claim donor auto-merge

## Upstream Hermes refresh workflow

When Hermes upstream changes, the intended flow is:

```bash
python update_hermes_with_brainstack.py /path/to/hermes-agent --pull --reinstall --doctor --runtime local
```

If the target runtime is Dockerized and the Docker image bakes Hermes source into the image, rebuild after reinstall:

```bash
python update_hermes_with_brainstack.py /path/to/hermes-agent --pull --reinstall --doctor --docker-rebuild --runtime docker
```

Docker helper after install:

```bash
cd /path/to/hermes-agent
./scripts/hermes-brainstack-start.sh start
./scripts/hermes-brainstack-start.sh rebuild
./scripts/hermes-brainstack-start.sh full
./scripts/hermes-brainstack-start.sh purge
./scripts/hermes-brainstack-start.sh reset
./scripts/hermes-brainstack-start.sh status
./scripts/hermes-brainstack-start.sh logs
```

This helper is intentionally small:

- `start` = bring the stack up
- `rebuild` = rebuild with cache and restart
- `full` = no-cache pull+build and restart
- `stop` = stop the running service
- `purge` = stop the service and clear conversational persistence, including Brainstack DB, state DB, and session replay files
- `reset` = purge conversational persistence and start the service again
- `status` = show compose status plus the current readiness summary from `gateway_state.json`
- `logs` = tail live logs
- `start` / `rebuild` / `full` wait for readiness instead of claiming success as soon as the container exists

## Doctor checks

`brainstack_doctor.py` validates:

- target checkout really looks like Hermes
- memory provider/plugin loader surfaces exist
- Brainstack plugin payload is present and importable
- Brainstack-only host helper is present
- `run_agent.py` gates legacy `memory` and `session_search` tool exposure
- `gateway/run.py` uses a Brainstack-aware session-boundary finalizer instead of legacy builtin-memory flush paths
- config selects Brainstack and builtin memory is off
- in `docker` mode: Docker compose uses `gateway run --replace`
- in `docker` mode: Docker compose uses a readiness-aware gateway healthcheck rather than a process-only healthcheck
- in `docker` mode: `scripts/hermes-gateway-healthcheck.py` exists
- in `docker` mode: the desktop launcher points at the intended Hermes checkout
- in `local` mode: Docker-specific checks are skipped and the doctor validates the Hermes checkout/config/plugin path without assuming container runtime

The doctor is designed to fail closed. If upstream Hermes removes a required provider surface, the right outcome is an explicit incompatibility report, not a silent half-wire.
