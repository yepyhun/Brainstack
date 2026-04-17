# Brainstack 1.01

This release hardens long-form style memory without bloating ordinary turns.

Highlights:

- Adds a canonical principal-scoped `preference:style_contract` lane for detailed Humanizer-style recall
- Keeps the compact active communication contract for normal turns
- Routes explicit style/rules recall through the model-backed routing seam instead of regex heuristics
- Migrates old corpus-backed style artifacts into the canonical profile lane and retires the old owner
- Hardens install-time Tier-2 writes by routing `auxiliary.flush_memories` through the main provider

This release also keeps the Brainstack-owned install path reproducible on a pre-existing Hermes checkout.

If you hit an issue or want to improve something, feel free to open a ticket or PR.
