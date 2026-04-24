# Phase 1 Implementation Contract

## Purpose

Freeze the minimum architecture decisions required before Brainstack implementation starts.

This file is the implementation-facing output of Phase 1.

## Frozen Host Contract

Hermes must interact with exactly one external memory provider:

- `brainstack`

Implementation form:

- `plugins/memory/brainstack/__init__.py`
- `plugins/memory/brainstack/plugin.yaml`
- optional `plugins/memory/brainstack/README.md`
- optional `plugins/memory/brainstack/cli.py`

## Architecture Invariants

These invariants are not optional implementation preferences. Future phases must preserve them unless an explicit architecture review replaces them.

1. Hermes sees exactly one external memory provider: `brainstack`.
2. The control plane owns policy and packing decisions, not canonical fact storage.
3. `profile`, `continuity`, `graph_truth`, and `corpus` each have one canonical owner.
4. RTK is a bounded sidecar, not a memory owner.
5. My-Brain-Is-Full-Crew is a workflow shell first, not a first-wave orchestrator.
6. Prior state must remain representable alongside newer state; no silent destructive overwrite.
7. Built-in Hermes memory displacement must stay a small-host-patch integration, not a deep fork.

Host ABI methods Brainstack must own:

- `initialize`
- `system_prompt_block`
- `prefetch`
- `queue_prefetch`
- `sync_turn`
- `get_tool_schemas`
- `handle_tool_call`
- `shutdown`
- `on_turn_start`
- `on_session_end`
- `on_pre_compress`
- `on_memory_write`
- `on_delegation`

## Hook Allocation Matrix

| Hermes hook | Brainstack responsibility | Must not become |
|---|---|---|
| `initialize` | bootstrap internal shelves, open local stores, load policy config | a heavy ingest/consolidation job |
| `system_prompt_block` | static operating guidance and compact stable profile cues | a dump of dynamic recall |
| `prefetch` | build the dynamic recall block for the current turn | a second static prompt |
| `queue_prefetch` | warm likely next-turn retrieval work in the background | mandatory foreground logic |
| `sync_turn` | cheap turn ingestion and light candidate extraction | blocking graph/corpus consolidation |
| `on_turn_start` | turn-aware policy tick and recency bookkeeping | a hidden recall side channel |
| `on_pre_compress` | preserve continuity before context collapse | a full batch re-index |
| `on_session_end` | heavier summarization and consolidation | the only place where durable memory is updated |
| `on_memory_write` | temporary compatibility bridge during displacement if needed | the normal steady-state write path |
| `get_tool_schemas` / `handle_tool_call` | remain empty by default in Phase 1 | the routine recall path |

## Memory Delivery Policy

### Static prompt block

Belongs in `system_prompt_block()`:

- compact operating guidance
- compact stable profile cues
- no large dynamic recall blocks

### Dynamic recall block

Belongs in `prefetch()`:

- current task continuity
- recent session carry-over
- graph truth snippets relevant to the active turn
- corpus snippets only when the control plane chooses to spend tokens

### Provider tools

Phase 1 default:

- no model-facing Brainstack tools

Escalation rule:

- tools may be added only when automatic hooks are proven insufficient and the tool reduces total net complexity

## Provider Tool Policy

Phase 1 default:

- Brainstack should expose no model-facing tools unless a later concrete need proves otherwise.

Reason:

- user priority strongly favors token savings
- Hermes already has a crowded tool surface
- provider hooks are sufficient for the first-wave architecture

If a provider tool is later added, it must pass all of these:

1. it cannot duplicate built-in tool behavior
2. it cannot become the normal path for routine recall
3. it must reduce net complexity instead of adding orchestration burden

## Ownership Map

### 1. Profile

Canonical owner:

- Brainstack profile shelf

Contains:

- user identity
- stable preferences
- long-lived style and workflow habits
- durable shared-work continuity anchors

Must not be owned by:

- corpus layer
- graph truth layer
- RTK
- My-Brain-Is-Full-Crew

### 2. Continuity

Canonical owner:

- Hindsight-style continuity layer

Contains:

- recent work state
- recent conversations
- active projects
- session summaries
- short-to-mid horizon continuity

Must not replace:

- profile shelf
- graph truth
- corpus

### 3. Graph Truth

Canonical owner:

- Graphiti-style graph truth layer

Contains:

- entities
- relations
- current state
- prior state
- supersession
- contradiction candidates

Special rule:

- old and new states must coexist until resolved; no destructive overwrite

### 4. Corpus

Canonical owner:

- MemPalace-style corpus layer

Contains:

- books
- textbooks
- notes
- large domain documents
- section-aware packing artifacts

Special rule:

- corpus may inform profile, continuity, and graph truth
- corpus may not silently become the canonical owner of those views

Donor baseline rule:

- future corpus integration should assume the latest upstream MemPalace release as the primary donor baseline, not the earlier evaluation snapshot
- Brainstack should consume MemPalace through a bounded adapter seam so upstream package, plugin, and storage improvements remain easy to adopt

## Synchronization Rules

1. Profile and continuity may exchange summaries, but profile remains canonical for stable personal facts.
2. Continuity may emit candidate entities and state changes to graph truth, but graph truth is canonical for temporal state.
3. Corpus may emit candidate facts and relations, but those are only canonical after being accepted into the proper owner layer.
4. No layer may silently overwrite another layer's canonical fact class.

## Control Plane Contract

The Mira-inspired control plane owns:

- injection policy
- collapse policy
- recall depth
- confidence-aware explanation depth
- provenance verbosity policy
- tool avoidance policy

The control plane does not own:

- durable fact storage
- canonical entity state
- canonical corpus storage
- stable personal profile storage

## Operating Policies

### Conflict handling

- surface contradictions instead of flattening them silently
- keep unresolved state conflicts visible until resolved

### Provenance behavior

- mention the basis by default in a compact way
- increase provenance detail when confidence is lower or the stakes are higher

### Uncertainty behavior

- prefer best-effort answers with explicit uncertainty over bluffing
- reserve hard abstention for cases where the system cannot ground the answer enough to be useful

### Temporal behavior

- preserve prior states alongside newer states
- treat supersession as a visible relation, not destructive overwrite

### Preference behavior

- learn stable user preferences strongly by default
- apply preferences automatically unless they conflict with a higher-priority correctness or safety constraint

### Operations behavior

- default to highly automatic memory handling
- surface contradictions and important confidence gaps instead of requiring routine manual maintenance

## Sidecar And Shell Contract

### RTK

Allowed:

- token/output discipline
- filtering
- shaping final payload size
- supporting tool-economy behavior

Forbidden:

- canonical memory ownership
- graph truth ownership
- profile ownership
- becoming a second control plane

### My-Brain-Is-Full-Crew

First-wave role:

- workflow shell
- skill-based upper layer
- workflow entrypoints
- higher-level user-facing routines

Forbidden in first wave:

- owning canonical memory
- replacing the control plane
- becoming a top-level second orchestrator

Promotion condition:

- only after Brainstack substrate and control plane are stable

## Native Hermes Displacement Contract

Built-in features to fully displace:

- built-in prompt memory
- built-in user profile prompt block
- built-in `memory` live tool path

Acceptable host patch scope:

- small changes in `run_agent.py`
- small changes in tool-loading or tool-surface filtering logic if needed

Not acceptable:

- deep long-lived host fork
- multiple competing memory hacks

## Allowed Edit Zones

Default edit zones for Brainstack work:

### Normal implementation zone

These are expected future touchpoints and do not require architecture escalation by themselves:

- `plugins/memory/brainstack/**`
- Brainstack-owned tests
- Brainstack-specific planning artifacts under `.planning/phases/01-*`

### Bounded host integration zone

These may be edited only for narrow integration reasons already frozen in this contract:

- `run_agent.py`
- `agent/memory_manager.py`
- `agent/memory_provider.py`
- built-in tool-surface filtering paths directly related to memory displacement

### Review-required zone

Edits outside the two zones above require an explicit architecture review first, because they are a sign that the integration boundary may be expanding:

- unrelated tool infrastructure
- unrelated orchestration/runtime surfaces
- broad prompt assembly paths outside the memory integration seam
- any new persistence owner outside the frozen Brainstack layer model

Escalation rule:

- if a future phase needs edits outside the normal implementation zone and bounded host integration zone, stop and record why the existing seam is insufficient before proceeding

## Smoke Check

Every phase that touches the Brainstack seam should preserve one compact smoke path that can be run before heavier verification.

Minimum smoke assertions:

1. the Brainstack provider loads successfully
2. built-in prompt memory can be disabled without boot failure
3. built-in user profile prompt handling can be disabled without boot failure
4. the live tool surface does not accidentally expose the displaced built-in `memory` path when Brainstack owns memory
5. GSD planning artifacts for the active phase still parse cleanly

Goal:

- catch silent integration regressions early with one cheap check instead of rediscovering them deep in later phases

## Extension Slot Table

| Extension class | Allowed shape | Example fit | Forbidden shape |
|---|---|---|---|
| Donor capability | copied idea or narrow adapter inside an existing owner layer | a NeuronFS-inspired indexing trick inside corpus ingestion | adding a new canonical memory owner |
| Sidecar | bounded helper that shapes payload size or execution efficiency | RTK for token/output discipline | owning profile, graph truth, or corpus canonically |
| Adapter enhancement | improvement to one named Brainstack layer or host bridge | better displacement filtering in `run_agent.py` | hidden second orchestrator |
| Orchestrator policy | control-plane rule about packing, avoidance, confidence, or provenance | Mira-style packing policy | durable fact storage outside owner layers |

Rule:

- no new core layer may be added without an ownership review that states what canonical fact class it owns and why an existing owner cannot own it

## Target Host Files For Phase 1 Execution

Primary files to read before implementation:

- `agent/memory_provider.py`
- `agent/memory_manager.py`
- `run_agent.py`
- `tools/memory_tool.py`
- `website/docs/developer-guide/memory-provider-plugin.md`
- existing provider examples under `plugins/memory/`

Primary files expected to change in later execution:

- `plugins/memory/brainstack/__init__.py`
- `plugins/memory/brainstack/plugin.yaml`
- `run_agent.py`
- tests covering plugin activation and memory displacement

## Acceptance Conditions For Phase 1

Phase 1 is complete only if all are true:

1. Brainstack host ABI is frozen.
2. Ownership is frozen for profile, continuity, graph truth, and corpus.
3. RTK and MBIFC boundaries are frozen.
4. Native-displacement patch scope is frozen.
5. The implementation team can start coding without reopening architecture ambiguity.
