# Phase 51 Graph Audit

## baseline

- repo: `/home/lauratom/Asztal/ai/finafina`
- full graph build:
  - parsed files: `1306`
  - total nodes: `29949`
  - total edges: `248122`
  - communities: `33`
  - cross-community edges: `7195`

## direct findings

### 1. The official memory seam is genuinely thin

Runtime seam evidence:
- `MemoryManager.build_system_prompt()` collects provider blocks and swallows provider failures
- `MemoryManager.prefetch_all()` collects provider prefetch blocks and treats provider failure as non-fatal
- `MemoryManager.sync_all()` delegates post-turn writes without making the host dependent on provider success
- `run_agent.py` only calls the memory seam in a few specific places:
  - initialization
  - system prompt build
  - turn-start
  - prefetch
  - sync
  - session-end / pre-compress hooks

Graph evidence:
- callers of `MemoryManager.prefetch_all()`:
  - only `run_conversation` and tests
- callers of `MemoryManager.build_system_prompt()`:
  - only `_build_system_prompt` and tests
- `MemoryManager` has direct tests in `tests/agent/test_memory_provider.py`

Verdict:
- this is real synergy, not paper synergy
- Brainstack is entering Hermes through the correct seam

### 2. The host remains architecturally sensitive around `run_agent`

Graph evidence:
- `run_agent.py::AIAgent.run_conversation` is one of the biggest hubs in the repo
  - total degree: `786`
- `run_agent.py` blast radius is high
- the architecture overview still flags high overall repo coupling

Meaning:
- even a correctly placed memory provider can become dangerous if it thickens the `run_conversation` path

Verdict:
- the current thin-shell direction is necessary
- any future attempt to move Brainstack logic back into host reply governance would be anti-synergistic

### 3. `MemoryManager` is thin, but it is still a high-sensitivity seam

Graph evidence:
- `agent/memory_manager.py` blast radius:
  - directly changed nodes: `23`
  - impacted nodes within 3 hops: `519`
  - additional files affected: `23`

Meaning:
- this is still the right seam
- but it is not a cheap seam
- a bad change here ripples widely through Hermes

Verdict:
- the seam is correct
- its sensitivity means donor/provider integration must stay simple and explicit

### 4. Brainstack remains too opaque for a fully comfortable verdict

Observed fact:
- after a full graph rebuild, the graph tools do not cleanly resolve:
  - `plugins/memory/brainstack/__init__.py`
  - `BrainstackMemoryProvider`
  as queryable nodes

Observed size:
- `plugins/memory/brainstack/__init__.py` = `1945` lines
- `plugins/memory/brainstack/retrieval.py` = `1224` lines
- `plugins/memory/brainstack/executive_retrieval.py` = `1912` lines
- `plugins/memory/brainstack/db.py` = `5268` lines

Meaning:
- runtime seam fit is better than before
- but inspectability is still weak
- a strict reviewer can fairly say:
  - “the plugin is in the right place, but it is still too large and too graph-opaque to call fully harmonious”

Verdict:
- this is not anti-synergy
- but it is still only partial synergy on the inspectability axis

### 5. The main remaining host architectural risk is not Brainstack-specific

Graph evidence:
- top bridges are dominated by gateway/platform classes
- top hub risk is dominated by:
  - `run_conversation`
  - gateway classes
  - CLI/doctor hubs
- the graph’s suggested questions point mostly at host bridge/hub risks, not at Brainstack becoming the top architectural chokepoint

Meaning:
- Brainstack is no longer obviously the thing dominating the host architecture
- this is good
- it supports the claim that Phase 50 moved the design in the correct direction

Verdict:
- positive signal for donor fit

## overall verdict

### final judgment

`partially synergistic`

### why not weaker

- Brainstack now uses the official Hermes memory-provider seam
- the host treats provider failures as non-fatal
- the ordinary chat path is no longer being justified by host-level Brainstack governance
- the largest host architectural risks are still general Hermes hubs, not obviously Brainstack takeover points

### why not stronger

- the Brainstack plugin remains very large in several core files
- the graph cannot cleanly surface the plugin as first-class queryable structure
- this means inspectability and maintenance proof still lag behind runtime seam fit
- in other words:
  - the integration is genuinely better than paper-only
  - but it is not yet elegant enough to call a masterpiece fit

## donor-fit gap map

1. **Gap: plugin graph invisibility**
- impact:
  - strict inspectors cannot easily trace the Brainstack plugin structure with the same tooling used for the rest of Hermes
- principle pressure:
  - `Truth-first / no "good enough"`
  - `Modularity / Upstream updateability`

2. **Gap: oversized internal modules**
- impact:
  - Brainstack may be in the right seam but still too large to be comfortable to evolve
- principle pressure:
  - `Donor-first`
  - `Zero heuristic sprawl`

3. **Gap: host seam sensitivity**
- impact:
  - `MemoryManager` and `run_conversation` are the right seams, but too much logic there would quickly re-thicken the host
- principle pressure:
  - `Donor-first`
  - `The donor-first elv marad`

## next-action reading

The next work should not ask:
- “how do we add more Brainstack behavior?”

It should ask:
- “how do we make the plugin easier to inspect, easier to prove, and easier to maintain without moving behavior back into the host?”

That means the likely correct follow-up is:
- decomposition and inspectability improvement inside Brainstack itself
- not another host feature phase
