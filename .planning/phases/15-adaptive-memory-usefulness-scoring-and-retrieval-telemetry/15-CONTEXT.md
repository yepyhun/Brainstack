# Phase 15 Context

## Why This Phase Starts Now

Phases `10.2` through `14.2` closed the core correctness gaps:

- ingest noise is filtered
- Tier-2 extraction and deterministic reconciliation exist
- temporal/provenance safety exists
- everyday recall and preference application are proven in live runtime

That makes adaptive retrieval optimization trustworthy enough to add now.

## What Problem This Phase Solves

Brainstack still treats recall usefulness too statically.

- profile rows keep a fixed `confidence`
- graph rows carry provenance and temporal metadata, but recall does not learn from repeated exposure
- the control plane does not record which rows were actually surfaced into working memory

So the system cannot yet tell the difference between:

- items that are repeatedly worth surfacing
- items that are repeatedly only fallback noise

## Architectural Constraints

- no new runtime
- no new storage layer
- no flat donor transplant
- no destructive pruning or deletion of memory records
- no fake answer-understanding logic that pretends to know whether the model truly used a fact

## Bounded Direction

Phase 15 should add:

- bounded retrieval telemetry on already surfaced rows
- metadata-based storage of telemetry inside existing `metadata_json`
- modest ranking adjustments that stay shelf-aware and non-destructive
- preservation of core identity / communication / shared-work facts

Phase 15 should not add:

- a second scoring service
- a universal Bayesian engine wired through the whole system
- answer-parsing speculation masquerading as truth

## Donor Guidance

Useful inspiration:

- `/home/lauratom/Asztal/ai/hermes-agent-port/agent/kernel_memory_feedback_priority.py`

Carry forward:

- usefulness telemetry
- repeated low-value detection ideas
- bounded ranking adjustments

Do not carry forward directly:

- a single flat ratio as the final Brainstack scoring truth

## Likely Code Surfaces

- `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/control_plane.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/db.py`
- `/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/retrieval.py`
- tests under `/home/lauratom/Asztal/ai/atado/Brainstack/tests/`
