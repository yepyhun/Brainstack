
<img width="1024" height="1536" alt="image" src="https://github.com/user-attachments/assets/c10a4ea1-76b7-45f5-93db-9f5eae98d9b3" />

# Brainstack

`Hermes-native` `local-first` `donor-grounded`

Brainstack gives Hermes a memory model instead of a memory blob.

It is a composite `MemoryProvider` for persistent agents: profile memory, session continuity, temporal graph truth, and corpus retrieval under one memory owner inside Hermes.

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
| **L3** | **[MemPalace](https://github.com/MemPalace/mempalace)** | large-corpus retrieval, source/chunk identity, packed cited evidence recall |

Additional patterns also shape the current code:

- **Hermes-LCM** for bounded transcript evidence fallback


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
- keep memory ownership inside Brainstack instead of letting three half-systems fight each other
- stay useful in real deployed runs, not just in architecture diagrams

## Current status

- runs inside Hermes-Agent as a direct `MemoryProvider` plugin
- augments Hermes through the native explicit-memory seam instead of replacing builtin user/profile writes
- keeps memory ownership in Brainstack while storage is split by responsibility
- uses `SQLite` for shell, session, profile, transcript, and lexical fallback state
- supports embedded `Kuzu` for L2 graph truth and reports explicitly if it is unavailable
- supports embedded `Chroma` for L3 semantic corpus retrieval and reports explicitly if it is unavailable
- is actively audited against the donor-first native-seam model
- explicit user/addressing truth remains Hermes-host owned
- transport-handle precedence and explicit-truth atomicity on live chat surfaces remain Hermes host seams, not Brainstack plugin seams
- explicit multi-rule pack fidelity and ordinary-turn compliance are proven on the Hermes host path, not by reintroducing Brainstack-owned behavior governance
- runtime handoff is read-only from Brainstack's side; scheduling, execution, and approval remain Hermes/runtime responsibilities

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
3. **[MemPalace](https://github.com/MemPalace/mempalace)** - For modular, high-performance retrieval and FTS/Semantic FUSION handling of large corpuses without massive token overhead.

That donor base is not the whole point. Brainstack's value is that it gives Hermes one memory owner for these jobs instead of leaving them as separate memory-shaped subsystems.

This shows up as a strict internal separation of concerns:

| Layer | Inspiration | Core Responsibility |
| :--- | :--- | :--- |
| **L1** | **Hindsight** | recency, session continuity, after-turn learning |
| **L2** | **Graphiti** | entity-relation-temporal graph, current/previous truth |
| **L3** | **MemPalace** | big corpus, FUSION context packing |

Additional patterns also influence the current code:

- **Hermes-LCM transcript pattern** for bounded raw transcript retention and temporal evidence fallback

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

On top of the shelves, Brainstack uses owner-first evidence assembly:

- high-stakes questions should not bluff from memory alone
- explicit profile questions should prefer compact native or mirrored profile recall
- temporal and explanatory questions should expand continuity and graph evidence
- transcript recall stays bounded and session-scoped
- graph recall keeps current truth, historical truth, inferred links, and conflicts separate instead of flattening them together

## What is already working

This repo is no longer just an architecture sketch.

What is currently true:

- the plugin runs inside Hermes as a real `MemoryProvider`
- native explicit writes stay host-owned and can be mirrored into Brainstack
- explicit multi-rule packs can remain as raw archival truth without requiring compiled behavior-policy re-growth
- ordinary turns no longer depend on a Brainstack-specific communication-governor lane
- graph, transcript, continuity, and corpus shelves remain distinct instead of collapsing into one flat memory blob
- doctor output distinguishes active backends from explicit degraded states instead of treating silent fallback as success
- release hygiene tooling rejects tracked private runtime state, local planning state, and high-confidence secret-shaped payloads
- recent-work operating truth is workstream-scoped so project status and agent assignments do not collapse into one canonical memory
- workstream recap evidence is typed and scoped, so compact operating state can anchor recap answers before broad continuity or corpus fallback
- explicit scoped workstream recap capture can create idempotent operating anchors without guessing workstream identity from prose
- store substrate checks expose schema and migration-ledger health through the doctor surface
- explicit backup/restore helpers and migration dry-run reports support safer local upgrades
- the installer recognizes Hermes' native interrupted-turn external-memory guard, so Brainstack follows the upstream host seam instead of forcing a stale local patch

Release posture:

- Brainstack is optimized for native Hermes integration first
- donor refreshes are explicit and reviewable, not silent rewrites
- benchmark artifacts are treated as supporting evidence, not runtime authority
- public payloads exclude private runtime state, local auth, sessions, and planning files

## Repo scope

This repository is a focused Brainstack slice containing:

- the Hermes-native Brainstack plugin code under `brainstack/`
- donor boundaries and refresh logic under `brainstack/donors/` and `scripts/`
- minimal host-compatibility payload under `host_payload/agent/`
- install and doctor tooling for Hermes checkouts

This repository intentionally does not ship Hermes host files like:

- `run_agent.py`
- `agent/prompt_builder.py`
- `tools/memory_tool.py`
- `gateway/session.py`
- private runtime trees such as `hermes-config/`
- local planning/workflow state such as `.planning/`

If a live defect is rooted in explicit-truth capture, transport metadata precedence, or user-surface greeting behavior, the fix belongs on the Hermes host seam unless it can be shown to be a true Brainstack provider defect.

## Repo layout

```text
brainstack/
docs/
host_payload/agent/
scripts/
brainstack_doctor.py
install_into_hermes.py
update_hermes_with_brainstack.py
```

## Included operational tooling

| Script | Role |
| :--- | :--- |
| `install_into_hermes.py` | Install Brainstack into a Hermes checkout |
| `update_hermes_with_brainstack.py` | Refresh Hermes upstream and reinstall Brainstack |
| `brainstack_doctor.py` | Validate install assumptions and fail closed when upstream changed something important |
| `scripts/brainstack_store_ops.py` | Explicit JSON backup, restore, and migration-report CLI for the SQLite store |
| `scripts/check_release_hygiene.py` | Fail release payloads that accidentally track private runtime state or high-confidence secrets |
| `scripts/brainstack_refresh_donors.py` | Report donor state and run bounded refresh workflow |

## Reproducible quality gates

Use these gates before publishing a release or changing memory-kernel behavior:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check .
python -m mypy brainstack scripts tests --explicit-package-bases --ignore-missing-imports
python scripts/brainstack_golden_recall_eval.py
python scripts/brainstack_multilingual_multimodal_gate.py
python scripts/check_release_hygiene.py --repo .
python install_into_hermes.py --help
python brainstack_doctor.py --help
```

The tracked test suite is paired with install and doctor smoke checks because Brainstack is a Hermes plugin: release readiness means the code passes locally and the target Hermes seam still verifies.

## Installation into Hermes

Brainstack is meant to be installed into a fresh Hermes checkout, not copied around by hand.

Dry-run compatibility check:

```bash
python install_into_hermes.py /path/to/hermes-agent --enable --doctor --dry-run --runtime docker
```

By default the installer uses `--host-patch-mode core`, which applies only Brainstack payload/config/dependency work plus minimal memory-provider seams. Use `--host-patch-mode compat` only for explicit host-runtime compatibility hotfixes, and `--host-patch-mode legacy` only for emergency rollback/testing of the previous broad host patch behavior.

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
| Host helper | Copies only Brainstack-specific runtime helpers; RTK sidecar wiring is not installed because upstream Hermes already owns tool-result budgeting natively |
| Host patching | Defaults to `--host-patch-mode core`; compatibility host edits require an explicit `compat` or `legacy` mode |
| Config | Sets `memory.provider: brainstack`, keeps builtin memory and builtin user profile enabled, and wires the `Kuzu` and `Chroma` paths |
| Docker support | Generates `scripts/hermes-brainstack-start.sh`, adds a readiness-aware healthcheck, and supports the same install flow as local mode |
| Verification | Writes a sanitized install manifest and can run doctor checks immediately |

Safety boundaries:

- unknown upstream host changes are surfaced through doctor checks
- secrets, private Hermes runtime config, local auth, session state, and `.planning/` stay out of release payloads
- donor refreshes stay explicit and inspectable
- API-first deployment remains separate from the Hermes-native plugin path

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

That keeps donor drift inspectable without turning updates into silent rewrites.

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

It validates that the target checkout still looks like Hermes, that the provider/plugin loader surfaces exist, that Brainstack is present and importable, that Hermes native explicit-memory surfaces remain enabled, and that config selects Brainstack without replacing the host's builtin profile write path. It also probes configured `Kuzu` and `Chroma` backend openability, checks read-only runtime handoff surfaces, and treats missing requested capabilities as explicit degraded states. In `docker` mode it checks readiness-aware health wiring and recognizes upstream-style runtime ownership normalization. In `local` mode it skips the Docker-specific assumptions.

If Hermes upstream removes a required provider surface, the correct outcome is an explicit incompatibility report, not a silent partial install.

## Current direction

The current corrective direction is narrow and concrete:

- keep Brainstack on the memory/state/policy side of the Hermes boundary
- reduce installer host edits toward native Hermes seams wherever upstream already provides the surface
- make backend degradation, runtime handoff, and recall packet selection inspectable before claiming confidence
- keep exact-fact, recent-work, and stale-residue handling universal rather than live-case-specific
- keep recent-work authority scoped by workstream instead of promoting unscoped idle summaries as canonical truth
