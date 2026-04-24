# External Memory Donor Source Map

Status: research note for post-69 roadmap planning. This is not an implementation plan and does not override `IMMUTABLE-PRINCIPLES.md`.

## Principle Filter

Only adopt competitor ideas when they satisfy:

- memory-kernel boundary, not scheduler/executor/governor ownership;
- donor-first modularity and upstream updateability;
- universal Brainstack improvement, not benchmark/live-case distortion;
- no keyword farm or language-specific heuristic sprawl;
- inspectable success path and measurable product quality impact;
- multilingual and multimodal extensibility.

## Source Files Checked

### Mnemosyne

- Provider/tool lifecycle: https://github.com/AxDSan/mnemosyne/blob/main/hermes_memory_provider/__init__.py
- Core BEAM memory: https://github.com/AxDSan/mnemosyne/blob/main/mnemosyne/core/beam.py

Adoptable patterns:

- Static memory tool schema export through provider.
- Tool dispatch for `remember`, `recall`, `sleep`, `stats`, `invalidate`, and structured triples.
- Provider lifecycle hooks: system prompt block, pre-turn prefetch, post-turn sync, session-end consolidation, builtin-memory mirroring.
- Simple operator ergonomics: local provider, explicit stats, explicit invalidation.

Do not copy blindly:

- Generic memory-blob behavior that erases Brainstack shelf authority.
- Assistant-authored conversation mirroring into durable truth without Brainstack authority/provenance rules.

### CerebroCortex

- Hermes integration: https://github.com/buckster123/CerebroCortex/blob/main/HERMES_INTEGRATE.md
- Core cortex pipeline: https://github.com/buckster123/CerebroCortex/blob/main/src/cerebro/cortex.py

Adoptable patterns:

- MCP/tool-first UX as an optional operator surface.
- Provider plugin concepts: prefetch, background sync, session summaries, MEMORY.md mirroring, focused tools.
- Recall pipeline concept: vector semantic seeds, associative expansion, scoring, access update, and explain option.
- Session/procedure style memory as recallable support state.

Do not copy blindly:

- Broad agent workflow ownership.
- Messaging, intention, or todo tools that make Brainstack a runtime governor.
- Unbounded dream/consolidation behavior.

### neural-memory

- Unified Python API: https://github.com/itsXactlY/neural-memory/blob/master/python/neural_memory.py
- README / design overview: https://github.com/itsXactlY/neural-memory

Adoptable patterns:

- Semantic memory plus graph connections.
- Bounded spreading activation / `think`-style expansion from known memory IDs.
- Manual and background consolidation concepts, only if inspectable and bounded.
- Tool separation: remember, recall, graph stats, dream/consolidation stats.

Do not copy blindly:

- GPU/LSTM/MSSQL complexity before Brainstack core proof is complete.
- Dream-engine branding or autonomous behavior without clear runtime boundaries.

### defaultmodeAGENT

- Memory index: https://github.com/EveryOneIsGross/defaultmodeAGENT/blob/main/agent/memory.py
- Hippocampus/rerank path: https://github.com/EveryOneIsGross/defaultmodeAGENT/blob/main/agent/hippocampus.py

Adoptable patterns:

- Attention/rerank idea as a bounded candidate-ranking technique.
- Compress-for-embedding while preserving original evidence for final output.

Do not copy blindly:

- Discord/personality-agent assumptions.
- Character/affect-driven behavior as memory-kernel policy.

## Roadmap Mapping

- Phase 70: Mnemosyne/CerebroCortex/neural tool surface, adapted to Brainstack shelves.
- Phase 71: Mnemosyne/CerebroCortex provider lifecycle and optional MCP/operator UX.
- Phase 72: Mnemosyne-style explicit remember plus Brainstack typed durable capture and supersession rules.
- Phase 73: Mnemosyne sleep plus neural/Cerebro consolidation, bounded and inspectable.
- Phase 74: Cerebro session/procedure memory, stripped of governance.
- Phase 75: Cerebro/neural associative expansion, bounded by Brainstack trace and authority.
- Phase 76: Brainstack-owned corpus ingest productization; competitors are weaker here, but their UX pressure makes this essential.
- Phase 77: Own Brainstack principle gap: multilingual/multimodal proof, because competitors do not sufficiently guarantee it.
