# Handoff

## Why This Exists
This file preserves the architecture truth gathered before context condensing.

## Host Findings
Latest Hermes memory architecture supports:

- one built-in provider
- one external provider
- additive external provider prompt block
- provider lifecycle hooks for:
  - initialize
  - prefetch
  - sync_turn
  - on_turn_start
  - on_pre_compress
  - on_session_end
  - on_memory_write

Important source files:

- `agent/memory_provider.py`
- `agent/memory_manager.py`
- `agent/builtin_memory_provider.py`
- `run_agent.py`
- `website/docs/developer-guide/memory-provider-plugin.md`
- `website/docs/user-guide/features/memory-providers.md`

## Architectural Conclusion
Do not register `Hindsight`, `Graphiti`, and `MemPalace` as separate peer Hermes providers.

Do implement:

- one external provider: `brainstack`

Inside that provider:

- `Hindsight`
- `Graphiti`
- `MemPalace`
- a working-memory control plane

## Current Integration Judgments

### Core
- Hindsight: yes
- Graphiti: yes
- MemPalace: yes

### Control Plane
- Mira: inspiration for working-memory and context packing, not a fourth live memory core

### Sidecars
- RTK: yes, as token-efficiency infra
- NeuronFS: donor ideas only
- My-Brain-Is-Full-Crew: optional upper shell only

### Donor Only
- Hermes PR #5641: too broad to be a foundation, but can donate improvements

## Important Constraint
The user wants a truly modular 3-layer stack with painless updates.

That requires:

- a stable outer provider contract
- clear internal ownership boundaries
- no dual-write ambiguity
- explicit extension slots

## Immediate Planning Risk
Do not slide back into:

- benchmark-driven design
- heuristic patching
- multi-core spaghetti
- overlapping truth stores
