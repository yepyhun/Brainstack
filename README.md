# Brainstack 🧠

**Brainstack** is a next-generation composite memory architecture designed for autonomous AI agents. 

Born out of the limitations of single-engine approaches, **Brainstack is fundamentally a fusion (a composite stack) inspired by and building upon three state-of-the-art memory paradigms:**
1. **[Hindsight]** - For temporal state preservation, bounded history, and preserving old states rather than destructively overwriting past knowledge.
2. **[Graphiti]** - For explicitly surfacing graph conflicts, tracking entity relationships, and managing temporal truths natively.
3. **[MemPalace]** - For modular, high-performance retrieval and FTS/Semantic FUSION handling of large corpuses without massive token overhead.

Brainstack merges the strengths of these engines into a single, highly mature **Proactive Context Management (PCM)** architecture to solve critical agent lifecycle vulnerabilities:
- **Ghost Vocabulary:** Forgetting essential domain-specific definitions when context windows compress.
- **Black Box Amnesia:** Forgetting the immediate trajectory, workflow, or "pending intent" during long-running tasks.
- **Split-Brain Corruption:** Concurrent write conflicts from review-agents and sub-agents.

---

## 🏗️ The 5-Shelf Composite Architecture

By analyzing the best mechanics of the *Hindsight/Graphiti/MemPalace* trio, Brainstack categorically routes memories into five intelligent "shelves" rather than a flat vector database:

1. **Profile Shelf (Semantic Anchoring):** Dynamically extracts and anchors durable identity, personal preferences, and "shared work" contexts via heuristics. It acts as an always-on dictionary, preventing *Ghost Vocabulary*.
2. **Continuity Shelf (Intent Carry-Over):** Inspired by stateful trackers, this fires on `pre_compress` and `session_end` hooks to snapshot the exact current workflow state and pending intent before the agent drops context, guaranteeing task seamlessness.
3. **Transcript Shelf:** An append-only raw conversational log (Hindsight-style) providing strict, bounded FTS evidence for temporal dispute resolution.
4. **Graph-Truth Shelf:** Handles structured entities, relation building, supersession logic (A natively overrides B over time), and captures explicit topological conflicts instead of silently auto-resolving them (Graphiti-style).
5. **Corpus Shelf:** Manages ingested external documents with optimized FTS FUSION matching and dynamic token-estimate packaging (MemPalace-style).

---

## ⚖️ The Control Plane (Risk-Adjusted Retrieval)

Brainstack doesn't blindly inject "Top K" vectors. Its Central Control Plane (`control_plane.py`) interprets the underlying intent and inherent risk of every user query to formulate a rigid **Working Memory Policy**:

- 🚨 **High-Stakes Queries** (e.g., *safety, dose, law, diagnosis, contract*):  
  Triggers `mode="deep"` and forces `tool_avoidance_allowed=False`. The agent is explicitly prohibited from hallucinating a "memory-only" response and must structurally verify information.
- 👤 **Preference Inquiries** (e.g., *prefer, like, usually*):  
  Triggers `mode="compact"`. It restricts noisy full-text transcripts and explicitly highlights the Profile Shelf for a natural, fast personality response.
- ⏳ **Explanatory / Temporal Queries** (e.g., *why, current, latest, changed*):  
  Increases continuity and graph-truth limits to provide deep historical context and causality.

---

## 🚀 Unified Singleton Design & Sidecars

Built natively as a `MemoryProvider` for Hermes Agent infrastructures. 
It functions as a central Singleton Control Unit, meaning any Background Sub-Agents (e.g., the RTK Sidecar or the My-Brain-Is-Full Crew) must tap directly into the shared `BrainstackStore`. This entirely eliminates duplicate SQLite connections, lock contention, and duplicate extractions across modular tools.
