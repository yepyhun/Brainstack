
<img width="1024" height="1536" alt="image" src="https://github.com/user-attachments/assets/c10a4ea1-76b7-45f5-93db-9f5eae98d9b3" />

# Brainstack

`Hermes-native` `local-first` `experimental`

Brainstack gives Hermes a memory model instead of a memory blob.

It is a composite `MemoryProvider` for persistent agents: profile memory, session continuity, temporal graph truth, and corpus retrieval under one runtime owner.

The promise is simple:

- better long-horizon memory for always-on Hermes agents
- less prompt sludge from blind transcript stuffing
- cleaner truth handling when preferences, facts, and large recalled bodies need different treatment

This repo is for people building serious Hermes-based second-brain systems. It is not trying to pretend that transcript search, vector recall, and profile tables are the same job.

## Core foundation

Brainstack is built from three donor lines, then reshaped into one Hermes-native memory system:

| Layer | Base | What Brainstack takes from it |
| :--- | :--- | :--- |
| **L1** | **[Hindsight](https://github.com/vectorize-io/hindsight)** | temporal carry-through, bounded recent history, after-turn continuity |
| **L2** | **[Graphiti](https://github.com/getzep/graphiti)** | entity/relation memory, temporal truth, conflict-aware graph state |
| **L3** | **[MemPalace](https://github.com/yepyhun/MemPalace)** | large-corpus retrieval, FTS/semantic fusion, packed evidence recall |

Additional patterns also shape the current code:

- **Hermes-LCM** for bounded transcript evidence fallback
- **RTK-style sidecar discipline** for token-aware auxiliary processing without taking memory ownership


## How a query flows through Brainstack

```text
User query
   |
   v
Risk + intent check
   |
   +--> profile recall      -> preferences, identity, stable user facts
   +--> continuity recall   -> recent session state, pending context
   +--> graph recall        -> current facts, relations, temporal truth
   +--> corpus recall       -> larger external knowledge and packed evidence
   +--> transcript fallback -> only bounded raw evidence when needed
   |
   v
Control plane packs the smallest useful evidence set
   |
   v
Hermes answers
   |
   v
After-turn learning updates the right shelf, not one giant memory blob
```

In plain language:

- Brainstack first decides what kind of question this is.
- Then it pulls from the right shelves instead of dumping everything into the prompt.
- Hermes gets a small, purpose-built evidence packet.
- After the answer, the new information is written back to the right place.

## Why Brainstack exists

Most agent memory stacks fail in predictable ways:

- they flatten profile, transcript, graph, and corpus into one blob
- they overwrite old facts instead of tracking change over time
- they split memory ownership across multiple subsystems that quietly disagree with each other
- they solve recall by stuffing more and more text back into the prompt

Brainstack takes the opposite approach:

- one live memory owner
- clear separation of responsibilities
- bounded evidence instead of transcript abuse
- temporal truth handled explicitly, not as an afterthought

Transcript is evidence. Graph is truth. Corpus is corpus. Profile is profile. That sounds obvious. In practice, it usually is not.

## What Brainstack is trying to do

- be one of the strongest practical local-first memory stacks for always-on Hermes agents
- combine temporal continuity, graph truth, and corpus retrieval in one system
- keep runtime ownership inside Brainstack instead of letting three half-systems fight each other
- stay useful in real deployed runs, not just in architecture diagrams

## Current status

- runs inside Hermes-Agent as a direct `MemoryProvider` plugin
- is intended to be the single live memory path when Hermes builtin memory is disabled
- keeps runtime ownership in Brainstack while storage is split by responsibility
- uses `SQLite` for shell, session, profile, transcript, and lexical fallback state
- uses embedded `Kuzu` for L2 graph truth
- uses embedded `Chroma` for L3 semantic corpus retrieval
- is experimental, working, and opinionated

## Quickstart

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

After install, run the doctor and confirm that Brainstack is the active memory provider.

## What Brainstack is built from

Brainstack is built from three donor lines, then re-composed into a single Hermes-native memory system:

1. **[Hindsight](https://github.com/vectorize-io/hindsight)** - For temporal state preservation, bounded history, and preserving old states rather than destructively overwriting past knowledge.
2. **[Graphiti](https://github.com/getzep/graphiti)** - For explicitly surfacing graph conflicts, tracking entity relationships, and managing temporal truths natively.
3. **[MemPalace](https://github.com/yepyhun/MemPalace)** - For modular, high-performance retrieval and FTS/Semantic FUSION handling of large corpuses without massive token overhead.

That donor base is not the whole point. Brainstack's value is that it gives Hermes one runtime owner for these jobs instead of leaving them as separate memory-shaped subsystems.

This shows up as a strict internal separation of concerns:

| Layer | Inspiration | Core Responsibility |
| :--- | :--- | :--- |
| **L1** | **Hindsight** | recency, session continuity, after-turn learning |
| **L2** | **Graphiti** | entity-relation-temporal graph, current/previous truth |
| **L3** | **MemPalace** | big corpus, FUSION context packing |

Additional patterns also influence the current code:

- **Hermes-LCM transcript pattern** for bounded raw transcript retention and temporal evidence fallback
- **RTK-style sidecar discipline** for token-aware auxiliary work without taking memory ownership

## What Brainstack adds on top

Using the donors directly would still leave a lot of hard integration work in the host.

Brainstack adds the parts that make the system usable as one memory kernel instead of a donor bundle:

- one live memory owner inside Hermes
- explicit shelf separation instead of a flat memory blob
- current truth, historical truth, and conflict state kept distinct
- bounded packing discipline so recall helps the turn instead of flooding it
- host-aware install, doctor, and boundary tooling so the memory layer can actually survive real runtime drift

## Current runtime architecture

Brainstack routes memory into five shelves instead of a flat memory blob:

| Shelf | Purpose |
| :--- | :--- |
| Profile shelf | Durable identity, preference, and shared-work anchors |
| Continuity shelf | Session carry-over, compression snapshots, and pending work state |
| Transcript shelf | Append-only raw turns used as bounded evidence, not as a second live memory engine |
| Graph-truth shelf | Entities, explicit relations, bounded inferred links, temporal state, supersession, and conflict surfacing |
| Corpus shelf | External documents, sectioning, bounded recall, and large-corpus packing |

Under those shelves, storage is split by responsibility:

| Responsibility | Backend |
| :--- | :--- |
| shell, session, profile, transcript state, lexical corpus fallback | `SQLite` |
| L2 graph truth | `Kuzu` |
| L3 semantic corpus retrieval | `Chroma` |

On top of the shelves, Brainstack uses a risk-aware control plane:

- high-stakes questions should not bluff from memory alone
- preference-style questions should prefer compact profile recall
- temporal and explanatory questions should expand continuity and graph evidence
- transcript recall stays bounded and session-scoped
- active communication rules are packed into a short internal contract and applied silently
- graph recall keeps current truth, historical truth, inferred links, and conflicts separate instead of flattening them together

## What is already working

This repo is past the "interesting architecture sketch" stage.

What is currently true:

- the broader deployed-live matrix is holding at `9 / 10`
- the principal-isolation bug that polluted profile state across users was repaired and re-proven
- the proactive carry-through seam was repaired enough to pass focused deterministic and live follow-up checks
- provenance and lifecycle instrumentation landed without measured ordinary-turn token regression in the mirrored scenario

That does not mean every hard problem is solved. It means the core shape is already working as a real memory system, and the remaining gains are mostly about retrieval precision and packing quality, not basic ownership or identity correctness.

Proof artifacts for the current phases live under `reports/`.

## What this repo is not claiming

- It is not a standalone API-first memory product yet.
- It is not a one-click upstream auto-update system.
- It is not the full Hermes repository.
- It does not claim automatic donor compatibility without review.

The current framing is simple: native Hermes integration first, shared local store second, standalone API later, only if it is intentionally built.

## Repo scope

This repository is a focused Brainstack slice containing:

- the Hermes-native Brainstack plugin code under `brainstack/`
- donor boundaries and refresh logic under `brainstack/donors/` and `scripts/`
- focused test slices under `tests/`
- optional RTK sidecar integration surface in `rtk_sidecar.py`
- proof artifacts under `reports/`

## Repo layout

```text
brainstack/
docs/
host_payload/agent/
reports/
scripts/
tests/
brainstack_doctor.py
install_into_hermes.py
rtk_sidecar.py
update_hermes_with_brainstack.py
```

## Included operational tooling

| Script | Role |
| :--- | :--- |
| `install_into_hermes.py` | Install Brainstack into a Hermes checkout |
| `update_hermes_with_brainstack.py` | Refresh Hermes upstream and reinstall Brainstack |
| `brainstack_doctor.py` | Validate install assumptions and fail closed when upstream changed something important |
| `scripts/brainstack_refresh_donors.py` | Report donor state and run bounded refresh workflow |
| `rtk_sidecar.py` | Optional token-aware sidecar surface |

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

| Area | Action |
| :--- | :--- |
| Plugin payload | Copies `brainstack/` into `plugins/memory/brainstack/` |
| Host helper | Copies `agent/brainstack_mode.py` and `rtk_sidecar.py` when the target checkout supports them |
| Host patching | Gates legacy `memory` and `session_search` tool exposure in Brainstack-only mode and routes session boundaries through a Brainstack-aware finalizer |
| Config | Sets `memory.provider: brainstack`, disables builtin memory and builtin profile memory, and wires the `Kuzu` and `Chroma` paths |
| Docker support | Generates `scripts/hermes-brainstack-start.sh`, adds a readiness-aware healthcheck, and supports the same install flow as local mode |
| Verification | Writes a sanitized install manifest and can run doctor checks immediately |

What it intentionally does not do:

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

Current updateability is the middle path:

- explicit donor registry
- explicit local adapter seams
- bounded refresh reporting
- local smoke verification

That is much cleaner than silent donor drift, but it is still not full automatic upstream syncing.

## Docker helper after install

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

The helper is intentionally small:

- `start` brings the stack up
- `rebuild` rebuilds with cache and restarts
- `full` does a no-cache pull, build, and restart
- `stop` stops the running service
- `purge` clears conversational persistence, including Brainstack DB, state DB, and session replay files
- `reset` purges conversational persistence and starts again
- `status` shows compose status plus readiness summary from `gateway_state.json`
- `logs` tails live logs

`start`, `rebuild`, and `full` wait for readiness instead of claiming success as soon as the container exists. `purge` and `reset` ask for an explicit `DELETE` confirmation before wiping memory and session state.

## Doctor checks

`brainstack_doctor.py` is designed to fail closed.

It validates that the target checkout still looks like Hermes, that the provider/plugin loader surfaces exist, that Brainstack is present and importable, that Brainstack-only helpers are present, that legacy `memory` and `session_search` exposure is properly gated, and that config really selects Brainstack with builtin memory turned off. In `docker` mode it also checks the readiness-aware health wiring. In `local` mode it skips the Docker-specific assumptions.

If Hermes upstream removes a required provider surface, the correct outcome is an explicit incompatibility report, not a silent partial install.

## Current direction

The next recorded corrective direction is narrow and concrete:

- better exact-fact turn selection
- better update and supersession preference for fresher values
- better packing fidelity for answer-bearing details
- bounded query decomposition only where it is actually needed
