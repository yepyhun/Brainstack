# Brainstack 🧠

**Brainstack** is a next-generation, context-aware memory architecture for autonomous AI agents, moving beyond basic semantic Vector/RAG stores. 

It natively implements the **Proactive Context Management (PCM)** specification to solve critical agent lifecycle vulnerabilities, specifically:
- **Ghost Vocabulary:** Forgetting essential domain-specific definitions when context windows compress.
- **Black Box Amnesia:** Forgetting the immediate trajectory, workflow, or "pending intent" during long-running tasks.
- **Split-Brain Corruption:** Concurrent write conflicts from review-agents and sub-agents.

---

## 🏗️ The 5-Shelf Architecture

Instead of dumping diverse data into a flat database, Brainstack categorically routes memories into five intelligent "shelves":

1. **Profile Shelf (Semantic Anchoring):** Dynamically extracts and anchors durable identity, personal preferences, and "shared work" contexts via robust heuristics. This actively prevents Ghost Vocabulary by acting as an always-on dictionary.
2. **Continuity Shelf (Intent Carry-Over):** Fires on `pre_compress` and `session_end` hooks to snapshot the exact current state and pending intent before the agent drops context, guaranteeing task seamlessness.
3. **Transcript Shelf:** An append-only raw conversational log providing strict, bounded evidence for temporal dispute resolution.
4. **Graph-Truth Shelf:** Handles structured entities, relation building, supersession logic (A natively overrides B), and captures explicit topological conflicts.
5. **Corpus Shelf:** Manages ingested external documents with optimized token-estimate packing and standard FTS matching.

---

## ⚖️ The Control Plane (Risk-Adjusted Retrieval)

Brainstack doesn't just blindly inject the "Top K" similar vectors. Its Central Control Plane (`control_plane.py`) parses the intent and inherent risk of every incoming user query to formulate a rigid **Working Memory Policy**:

- 🚨 **High-Stakes Queries** (e.g., *safety, dose, law, diagnosis, contract*):  
  Triggers `mode="deep"` and forces `tool_avoidance_allowed=False`. The agent is explicitly prohibited from hallucinating a "memory-only" response and must structurally verify information.
- 👤 **Preference Inquiries** (e.g., *prefer, like, usually*):  
  Triggers `mode="compact"`. It restricts noisy full-text transcripts and explicitly highlights the Profile Shelf for a natural, fast response.
- ⏳ **Explanatory / Temporal Queries** (e.g., *why, current, latest, changed*):  
  Increases continuity and graph-truth limits to provide deep historical context and causality.

---

## 🚀 Unified Singleton Design

Brainstack serves as the single source of truth across all background sub-agents (like the RTK Sidecar) via a unified `BrainstackStore` singleton. This entirely eliminates duplicate SQLite connections, lock contention, and duplicate extractions.

Designed natively as a highly coherent `MemoryProvider` for the Hermes Agent infrastructure.
