# Brainstack

Brainstack is a Hermes-native composite memory provider built for **persistent second-brain usage**:
always-on agents, long-lived user identity, durable preferences, evolving truths, and larger bodies of recalled knowledge without turning the prompt into sludge.

The current ambition is straightforward:

- be one of the strongest practical local-first memory stacks for this always-on agent / second-brain use case
- combine the best parts of temporal continuity, graph truth, and corpus retrieval
- keep them under one runtime ownership model instead of letting three half-systems fight each other

It currently runs **inside Hermes-Agent as a direct `MemoryProvider` plugin**, not as a standalone API-first memory server. Runtime memory ownership stays with Brainstack, while the storage layer is split by responsibility:

- `SQLite` for shell/session/profile/transcript state
- embedded `Kuzu` for L2 graph truth
- embedded `Chroma` for L3 semantic corpus retrieval

## Proof snapshot

What is already proven in this repository:

- **90% broader deployed-live pass rate** on the current 10-scenario matrix:
  - `9 / 10` in Phase `23`
  - `9 / 10` again after the Phase `24` correctness fixes in Phase `25`
- **100% pass** on the long-range relation-tracking bucket in the broader live matrix:
  - `4 / 4`
- **Cross-principal profile bleed was closed** in the targeted principal canary:
  - `bleed_detected = false`
- **Focused proactive carry-through repair passed** in deterministic and deployed-path follow-ups:
  - the constrained deterministic case kept the required dietary constraint
  - the negative control did not fabricate it
  - the focused live rerun passed
- **Broader live packet discipline stayed bounded** in the published 10-scenario matrix:
  - average selected row count: `6.7`
  - average transcript rows: `2.4`
  - average graph rows: `1.5`
  - average corpus rows: `0.0`
- **Bestie mirror instrumentation landed with 0% measured ordinary-turn token regression** for the added provenance/lifecycle slices:
  - `775 -> 775`
  - `1049 -> 1049`

What that means in plain language:

- Brainstack is already strong enough to sustain a credible deployed-live memory story.
- The hardest recent correctness seam was repaired and re-proven.
- Extra auditability was added without bloating the measured ordinary turn in the mirrored case.

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
   Entities, explicit relations, bounded inferred links, temporal state, supersession, and explicit conflict surfacing.
5. **Corpus shelf**  
   External documents, sectioning, bounded recall, and large-corpus packing.

On top of the shelves, Brainstack uses a **risk-aware control plane**:

- high-stakes questions suppress memory-only bluffing
- preference-style questions prefer compact profile recall
- temporal/explanatory questions expand continuity and graph evidence
- transcript recall is bounded and session-scoped
- active communication-style rules are packed into a short internal contract and
  should be applied silently instead of being echoed back to the user
- bounded retrieval telemetry can gently deprioritize non-core fallback rows
  without deleting them or overriding temporal truth
- graph recall keeps explicit current truth first, historical truth separate,
  inferred links bounded, and conflicts visible without flattening them into one blob

## What is true in the current codebase

- Brainstack is intended to be the **single live memory path** when Hermes builtin memory is disabled.
- L2 now separates **current explicit truth**, **historical truth**, **open conflicts**,
  and **bounded inferred links** in recall packaging instead of flattening them together.
- The donor-inspired parts are behind **explicit local adapters**:
  - `brainstack/donors/continuity_adapter.py`
  - `brainstack/donors/graph_adapter.py`
  - `brainstack/donors/corpus_adapter.py`
- Donor baselines are tracked via a **bounded refresh workflow**, not hidden copy-paste drift.
- The refresh script can report local adapter state and optionally run local smoke checks.
- The current Brainstack baseline is **embedded-backend based**:
  - `SQLite` keeps shell state and lexical corpus fallback
  - `Kuzu` is the active graph backend target
  - `Chroma` is the active corpus semantic backend target
- L1 now consumes a stable executive retrieval contract instead of hardcoding backend specifics.
- Cross-store ingest consistency is treated as shell work, not as optional follow-up glue.
- Conversation history now participates in semantic retrieval through the same embedded `Chroma` path used for corpus recall.
- Retrieved conversational evidence now carries explicit date labels when known, instead of relying only on implicit ordering.
- Prompt-side evidence priority is now explicit in the rendered working-memory block:
  - specific, non-conflicted recalled facts should outrank generic prior knowledge
  - this is intentionally narrower than a blind “always trust memory” rule

## Current proof status

The current codebase is past the broad donor-first recovery track, and the proof story is now stronger than a generic architecture prototype.

What is currently true:

- the broader deployed-live matrix is holding at **`9 / 10` (`90%`)**
- the principal-isolation correctness bug that polluted profile state across users was repaired and re-proven
- the proactive carry-through seam was repaired enough to pass focused deterministic and live follow-up checks
- the later selective `hermes-lcm` donor uptake improved auditability / diagnostics without adding measured ordinary-turn token overhead in the mirrored scenario

That means:

- the architecture recovery is materially working in live product terms, not only in internal shape
- the remaining weakness is narrower than before
- the main open ceiling is no longer broad memory ownership or principal isolation
- the remaining gaps are mostly about higher-precision retrieval and future host ergonomics

The next recorded corrective direction is therefore:

- better exact-fact turn selection
- better update/supersession preference for fresher values
- better packing fidelity for answer-bearing details
- bounded query decomposition only where truly needed

This repository should currently be read as:

- **architecturally recovered enough to prove real direction**
- **already able to support a credible live-memory story**
- **not yet at “claim final-boss solved” status**

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
  corpus_backend.py
  corpus_backend_chroma.py
  db.py
  graph_backend.py
  graph_backend_kuzu.py
  extraction_pipeline.py
  transcript.py
  graph.py
  corpus.py
  retrieval.py
  stable_memory_guardrails.py
  temporal.py
  provenance.py
  reconciler.py
  tier1_extractor.py
  tier2_extractor.py
  usefulness.py
  donors/
scripts/
  brainstack_doctor.py
  install_into_hermes.py
  brainstack_refresh_donors.py
  update_hermes_with_brainstack.py
tests/
rtk_sidecar.py
```

## Included operational tooling

The repository already includes the useful operational scripts you would actually want in a source tree:

- doctor / install / refresh:
  - `brainstack_doctor.py`
  - `install_into_hermes.py`
  - `update_hermes_with_brainstack.py`
  - `scripts/brainstack_doctor.py`
  - `scripts/brainstack_refresh_donors.py`
  - `scripts/install_into_hermes.py`
  - `scripts/update_hermes_with_brainstack.py`

## Published proof artifacts

The repository includes a small set of proof artifacts that are actually worth reading:

- Phase `23` broader deployed-live baseline
- Phase `24` correctness proofs:
  - principal-bleed canary
  - deterministic carry-through proof
  - focused deployed-path proactive rerun
- Phase `25` broader post-fix baseline and proactive variance check

These are intentionally narrower than “upload every log ever produced”. They are here to back the main claims in this README, not to turn the repo into a dump folder.

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
  - `plugins.brainstack.graph_backend: kuzu`
  - `plugins.brainstack.graph_db_path: $HERMES_HOME/brainstack/brainstack.kuzu`
  - `plugins.brainstack.corpus_backend: chroma`
  - `plugins.brainstack.corpus_db_path: $HERMES_HOME/brainstack/brainstack.chroma`
- writes a sanitized `.brainstack-install-manifest.json`
- runs doctor checks if requested
- supports both `docker` and `local` runtime modes through the same installer
- in `docker` mode, generates `scripts/hermes-brainstack-start.sh` inside the target Hermes checkout
- in `docker` mode, generates `scripts/hermes-gateway-healthcheck.py` and patches Compose to use readiness-aware health instead of process-only health
- keeps Brainstack as the owner of personal profile/style memory while still allowing procedural skill usage

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
- `purge` / `reset` ask for an explicit `DELETE` confirmation before wiping memory/session state
- `purge` / `reset` also clear hidden session replay under `/opt/data/sessions/`

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
