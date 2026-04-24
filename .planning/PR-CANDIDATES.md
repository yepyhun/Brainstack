# External PR Candidates

This file records candidate improvements that are worth discussing or accepting as external PRs.

Promotion note: the current approved candidates are deliberately deferred as non-canonical PullPhase candidates. They must not receive canonical phase numbers until the Brainstack memory-kernel proof/reliability chain is complete.

Current blocking canonical phases:
- Phase 65: strict memory-kernel doctor and query inspect surface
- Phase 66: golden recall eval harness and regression gate
- Phase 67: typed semantic evidence index for durable shelves
- Phase 68: Tier-2 execution reliability and bounded durable promotion
- Phase 69: graph recall honesty, semantic seed, and naming correction

The notes below remain the source rationale for future PR promotion and external PR review against Brainstack's architectural rules.

## Intake Rule

A candidate PR is only acceptable if it:
- stays donor-first and upstream-updateable
- avoids heuristic sprawl and locale-specific hacks
- improves the general Brainstack kernel rather than solving one narrow test
- keeps Brainstack bounded and token-disciplined
- does not reintroduce Brainstack as a behavior governor

## Current Approved Candidates

### 1. Global injection budget allocator

Status: approved as a strong external PR candidate
Priority: highest

Why this is worth doing:
- Brainstack already has bounded retrieval and per-shelf budgets
- the remaining gap is that budgeting is fragmented by shelf
- a stronger cross-shelf allocator should improve prompt discipline, relevance, and token efficiency

Expected direction:
- introduce one global working-memory allocator across profile, continuity, transcript, graph, corpus, and other eligible shelves
- preserve route-aware behavior from the control plane
- cut lower-value evidence first instead of letting each shelf budget independently

Anti-goals:
- no prompt stuffing
- no benchmark-only packing hacks
- no special-case logic for one user, one model, or one test

Relevant code areas:
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/control_plane.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/executive_retrieval.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/__init__.py`

### 2. Stronger hybrid retrieval fusion

Status: approved as a strong external PR candidate
Priority: high

Why this is worth doing:
- Brainstack already has keyword retrieval and semantic retrieval
- Chroma is already active and semantic scores are already present
- the opportunity is to make the fusion cleaner, stronger, and more coherent across shelves

Expected direction:
- improve fusion between FTS-style keyword matching and semantic similarity
- keep retrieval bounded
- prefer general ranking improvements over per-query heuristics

Anti-goals:
- do not treat this as "turn Chroma on"
- no giant query-specific rerank farm
- no regression into opaque benchmark tuning

Relevant code areas:
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/executive_retrieval.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/db.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/corpus_backend_chroma.py`

### 3. Wiki as a corpus-backed knowledge source

Status: approved with tighter scope
Priority: medium

Why this is worth doing:
- there is real value in institutional knowledge and environment notes
- it can help migration from other memory setups without forcing Brainstack to become a direct donor-mount system

Expected direction:
- implement wiki as a corpus ingestion source or bounded doc kind
- keep it inside the existing bounded corpus shelf model
- prefer reusable ingestion and retrieval over direct prompt injection

Anti-goals:
- no raw wiki snippet dumping into the system prompt
- no special donor-magic shelf that bypasses normal bounded retrieval
- no loose uncontrolled file stuffing

Relevant code areas:
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/donors/registry.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/db.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/executive_retrieval.py`

### 4. Hermes-core stable extension seams / installer patch reduction

Status: approved strategically, but not a quick win
Priority: medium-high

Why this is worth doing:
- Brainstack is already a real plugin
- the remaining issue is that host integration still depends on too many patch-heavy seams
- reducing installer patch-sprawl is strategically important for maintainability and upstream survivability

Expected direction:
- move more host integration points toward stable Hermes extension seams
- reduce anchor-based patching in the installer
- keep Brainstack thin where Hermes should own the host seam

Anti-goals:
- do not reframe this as "Brainstack needs to become a plugin"
- no local-only patch shortcuts
- no parallel host architecture beside Hermes

Relevant code areas:
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/scripts/install_into_hermes.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/__init__.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/README.md`

## Explicitly Deferred

These were discussed, but are not currently approved as active PR targets:
- cross-instance fact sync
- GUI / control panel

Reason:
- both are higher-risk or lower-leverage right now than retrieval, budgeting, corpus integration, and installer seam cleanup
- both are more likely to expand scope before strengthening the kernel itself
