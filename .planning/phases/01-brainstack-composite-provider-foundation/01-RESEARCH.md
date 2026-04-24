# Phase 1 Research

## User Constraints

Copied from the locked Phase 1 context and later accepted decisions.

- one Hermes-facing external provider called `brainstack`
- internal layers:
  - `Hindsight`
  - `Graphiti`
  - `MemPalace`
  - Mira-inspired control plane
- full displacement of built-in Hermes memory behavior and built-in user-profile behavior
- user priority is effectively tied at the top between:
  - agent smartening / continuity
  - token savings
  - graph / temporal truth
- large corpus handling is a very close second priority
- separate stable shelf for personal identity, preferences, and shared work continuity
- broad first-wave scope rather than a narrow pilot
- max-savings default control philosophy
- RTK included early as a real sidecar
- My-Brain-Is-Full-Crew included early, but as a workflow shell first
- conflicts should be surfaced and asked about rather than silently flattened
- provenance should be visible by default but not spammy; stronger when confidence is lower or stakes are higher
- preserve prior states and temporal change instead of destructive overwrite
- deep corpus integration ambition, not shallow search-only handling
- preferences should be learned strongly and applied automatically
- highly automatic, low-devops operating model with contradiction surfacing
- real agent/personality feel first, study-companion value second [VERIFIED: .planning/phases/01-brainstack-composite-provider-foundation/01-CONTEXT.md]

## Phase Question

What must be true for Phase 1 planning to be sound?

1. The Hermes host-facing ABI must be frozen. [VERIFIED: agent/memory_provider.py]
2. Internal ownership of `profile`, `continuity`, `graph_truth`, and `corpus` must be unambiguous. [VERIFIED: .planning/REQUIREMENTS.md]
3. Native-memory displacement must be scoped to a small compatibility patch, not a deep fork. [VERIFIED: .planning/REQUIREMENTS.md, run_agent.py]
4. Sidecars and workflow shell must be bounded so they do not create a second brain or a second orchestrator on day one. [VERIFIED: .planning/STATE.md]

## Standard Stack

- Hermes host integration should be implemented as a normal memory provider plugin under `plugins/memory/brainstack/` with a `MemoryProvider` implementation and `plugin.yaml`. [VERIFIED: website/docs/developer-guide/memory-provider-plugin.md]
- The host ABI for the plugin is the `MemoryProvider` base class with the relevant lifecycle and optional hooks:
  - `initialize`
  - `system_prompt_block`
  - `prefetch`
  - `queue_prefetch`
  - `sync_turn`
  - `get_tool_schemas`
  - `handle_tool_call`
  - optional:
    - `on_turn_start`
    - `on_session_end`
    - `on_pre_compress`
    - `on_memory_write`
    - `on_delegation` [VERIFIED: agent/memory_provider.py]
- Hermes loads generic tool definitions first, then appends memory-provider tool schemas from the active memory manager. [VERIFIED: run_agent.py]
- Hermes currently supports the built-in provider plus at most one external provider; a second external provider is explicitly rejected by `MemoryManager.add_provider()`. [VERIFIED: agent/memory_manager.py]
- The built-in prompt-memory path can already be disabled via:
  - `memory_enabled: false`
  - `user_profile_enabled: false` [VERIFIED: run_agent.py]
- The built-in `memory` tool is still present on the live tool surface by default because the tool list is assembled before provider tool injection and independently of the memory config flags. [VERIFIED: run_agent.py, tools/memory_tool.py]
- The external provider system prompt block is additive, and provider prefetch output is fenced as memory context rather than mixed into user text. [VERIFIED: agent/memory_manager.py, run_agent.py]
- Existing provider examples worth imitating structurally:
  - `plugins/memory/hindsight/__init__.py`
  - `plugins/memory/mem0/__init__.py`
  - `plugins/memory/openviking/__init__.py` [VERIFIED: plugin source files]

## Architecture Patterns

### 1. One Provider Outside, Multiple Layers Inside

The correct host pattern is:

- Hermes sees exactly one external provider: `brainstack`
- `brainstack` internally delegates to:
  - Hindsight-style continuity layer
  - Graphiti-style graph truth layer
  - MemPalace-style corpus layer
  - one control plane that decides packing, recall depth, and tool avoidance [VERIFIED: agent/memory_manager.py, .planning/REQUIREMENTS.md]

This pattern fits Hermes' one-external-provider rule and preserves update safety better than registering multiple peer providers. [VERIFIED: agent/memory_manager.py, .planning/REQUIREMENTS.md]

### 2. Clear Ownership by Memory View

Recommended ownership model:

- `profile`
  - stable personal shelf
  - user identity
  - strong preferences
  - shared work continuity anchors
- `continuity`
  - recent sessions
  - turn/session summaries
  - active work state
- `graph_truth`
  - entities
  - relations
  - current/prior state
  - supersession
  - contradiction surfacing
- `corpus`
  - books
  - textbooks
  - notes
  - long-form domain material
  - section-aware packing [VERIFIED: .planning/PROJECT.md, .planning/REQUIREMENTS.md]

The planner should treat `profile` and `continuity` as related but not identical. The user explicitly wants a separate stable shelf, so `profile` must not be absorbed into generic corpus or graph storage. [VERIFIED: .planning/STATE.md]

### 3. Control Plane Is a Policy Layer, Not a Fourth Memory Store

The Mira-inspired control plane should own:

- what gets injected
- what stays collapsed
- confidence-aware explanation depth
- provenance verbosity policy
- tool avoidance thresholds [VERIFIED: .planning/STATE.md, .planning/phases/01-brainstack-composite-provider-foundation/01-01-PLAN.md]

The control plane should not become:

- a second graph store
- a duplicate continuity store
- a place where facts are re-canonized outside the owned layers [ASSUMED]

### 4. Sidecars and Shells Must Stay Bounded

- RTK belongs as an early sidecar for token/output discipline, not as a competing memory substrate. [VERIFIED: .planning/REQUIREMENTS.md]
- My-Brain-Is-Full-Crew belongs first as a workflow shell built from skills and workflow entrypoints, not as a day-one top-level orchestrator. [VERIFIED: .planning/STATE.md]

## Don't Hand-Roll

- Do not hand-roll a multi-provider host hack that bypasses the one-external-provider limit. Hermes already enforces the limit. [VERIFIED: agent/memory_manager.py]
- Do not hand-roll a deep Hermes fork just to replace memory. The requirement is explicitly one provider plus small compatibility patches only. [VERIFIED: .planning/REQUIREMENTS.md]
- Do not hand-roll a second canonical store for the same fact class. The architecture requirement explicitly forbids dual-write ambiguity without a synchronization rule. [VERIFIED: .planning/REQUIREMENTS.md]
- Do not hand-roll a custom top-level orchestrator around My-Brain-Is-Full-Crew in Phase 1. That would compete with the Brainstack control plane too early. [VERIFIED: .planning/STATE.md]
- Do not hand-roll a shallow search-only corpus path and call it done. The user explicitly wants deep corpus integration ambition. [VERIFIED: .planning/STATE.md]
- Do not hand-roll silent conflict resolution. The user wants surfaced contradictions and temporal coexistence of old/new state. [VERIFIED: .planning/STATE.md]

## Common Pitfalls

### Pitfall 1. Built-in Memory Is Not Fully Gone Just Because Config Flags Are Off

The built-in prompt-memory blocks are controlled by `memory_enabled` and `user_profile_enabled`, but the built-in `memory` tool is still part of the generic tool surface unless explicitly removed. [VERIFIED: run_agent.py, tools/memory_tool.py]

Planning implication:

- Phase 1 must include a small host compatibility patch to remove or bypass the built-in `memory` tool from the live path when Brainstack owns memory completely. [ASSUMED from verified call sites and guards]

### Pitfall 2. Flush Logic Assumes the Built-in Memory Tool Name

The flush path returns early if `"memory"` is not in `valid_tool_names` or if no memory store exists. That is good because it means removing the built-in memory tool should fail closed rather than crash. [VERIFIED: run_agent.py]

Planning implication:

- it should be feasible to remove the built-in tool from the live surface without needing a large flush-system rewrite [ASSUMED]

### Pitfall 3. `sync_turn()` Must Stay Non-Blocking

The plugin docs explicitly say `sync_turn()` must be non-blocking, and the existing providers use background threads or async helpers. [VERIFIED: website/docs/developer-guide/memory-provider-plugin.md, plugins/memory/hindsight/__init__.py, plugins/memory/mem0/__init__.py]

Planning implication:

- deep corpus formation, graph extraction, and consolidation must not live directly on the foreground request path

### Pitfall 4. Provider Tools Can Cause Tool Surface Bloat

Provider tools are appended to the existing tool surface. If Brainstack exposes too many tools, token costs and decision complexity increase. [VERIFIED: run_agent.py]

Planning implication:

- Brainstack Phase 1 should prefer:
  - zero provider tools, or
  - a very small bounded tool surface
- and rely primarily on automatic recall/prefetch/sync hooks [ASSUMED]

### Pitfall 5. System Prompt and Prefetch Can Double-Count Memory

Hermes supports both `system_prompt_block()` and `prefetch()`. If the same memory class is injected in both places, prompt bloat and conflicting instructions appear. [VERIFIED: agent/memory_provider.py, agent/memory_manager.py, run_agent.py]

Planning implication:

- Phase 1 must define which memory classes belong in:
  - static prompt block
  - dynamic prefetch block
  - tool surface

### Pitfall 6. Sidecars Can Quietly Recreate Ownership Ambiguity

If RTK filters content that the control plane is already shaping, or if My-Brain-Is-Full-Crew starts making routing decisions that belong to the control plane, ownership becomes fuzzy again. [ASSUMED]

Planning implication:

- Phase 1 must freeze sidecar and shell boundaries before implementation

## Code Examples

### Provider Skeleton To Follow

Use the standard Hermes plugin layout:

```text
plugins/memory/brainstack/
  __init__.py
  plugin.yaml
  README.md
  cli.py            # optional
```

[VERIFIED: website/docs/developer-guide/memory-provider-plugin.md]

### Host ABI Reference Files

- `agent/memory_provider.py`
- `agent/memory_manager.py`
- `website/docs/developer-guide/memory-provider-plugin.md`
- `plugins/memory/hindsight/__init__.py`
- `plugins/memory/mem0/__init__.py`
- `plugins/memory/openviking/__init__.py` [VERIFIED: local codebase]

### Concrete Hook Split To Plan Around

Recommended hook allocation:

- `initialize`
  - connect internal stores and load profile-scoped config
- `system_prompt_block`
  - static operating guidance only
- `prefetch`
  - dynamic recall block
- `queue_prefetch`
  - background warm-up for next turn
- `sync_turn`
  - cheap asynchronous ingestion only
- `on_turn_start`
  - turn-aware policy tick
- `on_pre_compress`
  - preserve insights before context collapse
- `on_session_end`
  - heavier consolidation
- `on_memory_write`
  - temporary bridge only if the built-in memory tool still exists during transition [VERIFIED: agent/memory_provider.py, agent/memory_manager.py]

## Planning Implications

### High Confidence

1. Phase 1 should plan `brainstack` as a normal Hermes memory plugin, not as a forked runtime feature. [VERIFIED: plugin docs, memory_provider.py]
2. Phase 1 must explicitly include the small built-in-memory-tool displacement patch in scope, because config flags alone do not remove the tool surface. [VERIFIED: run_agent.py, tools/memory_tool.py]
3. Phase 1 must freeze ownership across the four memory views before any deep implementation begins. [VERIFIED: .planning/REQUIREMENTS.md]
4. Phase 1 should keep My-Brain-Is-Full-Crew as a workflow shell and RTK as a bounded sidecar from day one. [VERIFIED: .planning/STATE.md]

### Medium Confidence

1. Brainstack should start with zero or very few provider tools and prefer automatic behavior through hooks. [ASSUMED]
2. The stable personal shelf should probably sit logically above generic continuity summaries and below graph/corpus layers, with explicit synchronization rules instead of shared write access. [ASSUMED]
3. The cleanest Phase 1 code split is likely:
   - one host-facing provider file
   - one internal boundary module per memory view
   - one control-plane policy module
   - one sidecar/shell policy module [ASSUMED]

## Recommended Phase 1 Output

The final Phase 1 plan should leave implementation with these concrete artifacts to create next:

1. `plugins/memory/brainstack/__init__.py`
   - host-facing provider
2. internal ownership/boundary modules
   - profile
   - continuity
   - graph_truth
   - corpus
   - control plane
3. minimal Hermes compatibility patch
   - remove or bypass built-in `memory` live-path dependence when Brainstack fully owns memory
4. explicit sidecar/shell boundary notes
   - RTK
   - My-Brain-Is-Full-Crew

## Confidence Summary

- Hermes plugin ABI and one-provider host rule: HIGH [VERIFIED: local codebase]
- Built-in prompt-memory disable path: HIGH [VERIFIED: local codebase]
- Need for a small built-in `memory` tool displacement patch: HIGH on the existence of the issue, MEDIUM on the exact patch shape [VERIFIED + ASSUMED]
- Brainstack internal ownership model: HIGH on necessity, MEDIUM on exact file/module split [VERIFIED + ASSUMED]
- Keep MBIFC as workflow shell first: HIGH [VERIFIED: locked project decisions]
