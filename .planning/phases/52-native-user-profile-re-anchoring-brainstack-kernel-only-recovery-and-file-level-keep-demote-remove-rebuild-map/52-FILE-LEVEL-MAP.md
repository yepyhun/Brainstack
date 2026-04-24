# Phase 52 File-Level Keep / Demote / Remove / Re-anchor

## baseline

- upstream host baseline: `/home/lauratom/Asztal/ai/finafina`
- architectural reading:
  - native Hermes owns explicit built-in memory/profile storage
  - Brainstack should live behind the memory-provider seam
  - the seam, not the current markdown filenames alone, is the product contract

## authority precedence target

This phase assumes the following precedence model:

- explicit user identity:
  - native Hermes first-class
  - Brainstack mirror/support
- explicit user preference:
  - native Hermes first-class
  - Brainstack mirror/support
- explicit communication/style rule packs:
  - native Hermes may hold the explicit user-facing profile truth
  - Brainstack may retain bounded archival canonical recall
  - ordinary chat may not be governed by that archival lane by default
- operating truth:
  - Brainstack first-class
- task truth:
  - Brainstack first-class
- transcript evidence:
  - Brainstack supporting evidence
- graph/corpus evidence:
  - Brainstack supporting evidence

If any implementation step would produce dual primacy for a truth class, that step is wrong.

## keep as native host anchors

These files should remain the first-class explicit profile path.

### `run_agent.py`
- keep as the host entry point that:
  - enables built-in memory and user-profile loading
  - runs built-in memory review prompts
  - bridges built-in writes to the external memory provider via `self._memory_manager.on_memory_write(...)`
- do not move explicit user-profile primacy out of this path
- use it as the place where native explicit writes and review-driven profile saves stay first-class

### `tools/memory_tool.py`
- keep as the canonical explicit write/read surface for:
  - `USER.md`
  - `MEMORY.md`
- this is the right place for explicit user facts and preferences to land first
- the contract should anchor to this write surface, not to the file names in isolation

### `agent/memory_manager.py`
- keep as the only coordination seam between:
  - built-in memory provider
  - one external provider
- this file is the correct place for mirroring built-in writes outward
- any re-anchor should prefer this bridge over direct Brainstack-first explicit writes
- this seam should own one-way mirror semantics, not ad hoc Brainstack-first profile writes

### `agent/memory_provider.py`
- keep as the contract that limits what an external memory provider is supposed to be
- this file proves the provider is additive, not the host’s main behavior engine

### `agent/prompt_builder.py`
- keep as the place that frames user profile as user truth, not runtime truth
- this should remain aligned with native `USER.md` semantics

## keep as Brainstack kernel

These files remain aligned with a true memory-kernel role.

### `plugins/memory/brainstack/__init__.py`
- keep as provider entry point and orchestration shell
- retain:
  - initialize
  - prefetch
  - sync_turn
  - shutdown
- reduce only the parts that imply profile or behavior primacy

### `plugins/memory/brainstack/db.py`
- keep as Brainstack-local storage and reconciliation substrate
- still needed for:
  - continuity
  - transcript
  - task / operating truth
  - graph / corpus
  - behavior-contract archival storage if retained in bounded form

### `plugins/memory/brainstack/retrieval.py`
- keep as retrieval packing / memory surfacing
- continue to serve:
  - transcript evidence
  - continuity
  - task / operating truth
  - graph / corpus
- remove any residual assumption that it is the primary owner of explicit user profile
- explicitly remove profile+graph fallback rebuilding of first-class communication contract authority once native explicit profile generation exists

### `plugins/memory/brainstack/executive_retrieval.py`
- keep as donor-aligned recall/orchestration logic
- further simplify only if it still acts like reply-path governance

### `plugins/memory/brainstack/transcript.py`
### `plugins/memory/brainstack/task_memory.py`
### `plugins/memory/brainstack/operating_truth.py`
### `plugins/memory/brainstack/reconciler.py`
### `plugins/memory/brainstack/extraction_pipeline.py`
### `plugins/memory/brainstack/graph*.py`
### `plugins/memory/brainstack/corpus*.py`
- keep as kernel machinery
- these are memory-system files, not host behavior-governance files

## demote to bounded or archival roles

These files are not useless, but they are too strong if treated as first-class profile authority or ordinary-chat governance.

### `plugins/memory/brainstack/profile_contract.py`
- demote from “parallel explicit profile owner” to:
  - bounded ingress helper
  - auxiliary reconciliation support
  - recall formatting helper where needed
- it should not outrank native `USER.md`
- if it extracts profile-like facts from chat, those must remain supporting/candidate until the native explicit path confirms them
- transcript-derived style atoms here must not regrow a first-class communication/profile authority once native explicit profile truth exists

### `plugins/memory/brainstack/style_contract.py`
- demote to explicit archival / recall role
- keep for:
  - canonical recall when the user explicitly asks for rules
  - archival style history
- do not let it become ordinary-turn behavior pressure by default
- if native Hermes stores explicit communication preferences, Brainstack should mirror or archive them rather than become the only explicit owner
- if native communication preferences are unavailable, this file may expose bounded archival recall or stale mirrored state, not silently become a new ordinary-turn governor

### `plugins/memory/brainstack/behavior_policy.py`
- demote to bounded advisory / archival support
- it may still compile explicit style contracts, but should not be the center of ordinary reply behavior

### `plugins/memory/brainstack/output_contract.py`
- demote to explicit or bounded validation surfaces only
- not a general-purpose ordinary chat delivery governor

### `plugins/memory/brainstack/control_plane.py`
- demote residual routing/governance pressure
- keep only what is necessary for memory-owned routing, not broad chat steering
- keep query/shelf planning and owner-first recall assembly
- remove any residual ordinary-turn style-governance escalation that would recreate a reply-shaping behavior engine

### `plugins/memory/brainstack/tier1_extractor.py`
### `plugins/memory/brainstack/tier2_extractor.py`
- demote their authority over explicit profile truth
- extracted preferences may remain candidates or augmentation signals
- they should not outrank explicit native profile writes
- they should also not back-door a new explicit profile authority after re-anchor

## remove or sharply reduce

These are the parts that most directly re-created the wrong product shape.

### host-visible or ordinary-turn behavior governance
- any remaining path where Brainstack:
  - blocks ordinary replies
  - strongly shapes ordinary replies through rule pressure
  - acts like a second behavior engine

### custom profile primacy from free chat
- any logic that lets Brainstack-derived profile/style lanes become the first-class explicit profile owner for ordinary user facts

### duplicate explicit profile truth
- if the same kind of user fact can land first in Brainstack custom profile state instead of native `USER.md`, that path should be cut or sharply reduced

## re-anchor / rebuild

These seams should be rebuilt around native writes instead of Brainstack-first writes.

### built-in write mirror path
- anchor explicit writes here:
  - `tools/memory_tool.py`
  - `run_agent.py`
  - `agent/memory_manager.py`
  - `agent/memory_provider.py`
- rule:
  - native write first
  - Brainstack mirror second
- one-way idempotent mirror rule:
  - carry `native_write_id`
  - carry `source_generation`
  - carry `mirrored_from = native_profile`
  - never emit a mirrored native record back upstream as a new explicit native write
- migration rule:
  - if current live truth exists only in Brainstack, the re-anchor batch must explicitly move/supersede/archive it so the native path becomes canonical

### Brainstack profile ingestion
- rebuild Brainstack profile handling so it prefers:
  - mirrored built-in `USER.md` facts
  - explicit archival memory truth
  - bounded augmentation
- not raw ordinary chat inference as first-class profile authority
- current candidate/extracted profile state must be audited for:
  - keep as support
  - migrate to native explicit truth
  - retire as redundant or shadow authority
- if native explicit authority is unavailable:
  - allow only `stale mirrored snapshot` or `no native explicit authority available`
  - do not synthesize a replacement first-class explicit truth from residue

### explicit style handling
- rebuild style handling so:
  - explicit rule packs can still be archived and recalled
  - ordinary chat does not depend on them as a hard governance layer
- explicitly close:
  - transcript-derived style atom regeneration in `profile_contract.py`
  - profile+graph communication-contract rebuild in `retrieval.py`

## parity surfaces to re-anchor in the same phase

### `README.md`
- remove brainstack-first setup language if native explicit-profile primacy becomes the target architecture
- describe Brainstack as memory kernel plus mirror/augmentation layer

### `install_into_hermes.py`
- stop installing or validating a brainstack-first host state if the target model is native explicit-profile primacy
- ensure installer output matches the new authority contract

### `scripts/brainstack_doctor.py`
- update checks that currently encode brainstack-first expectations
- doctor must validate the re-anchored architecture rather than the old single-live-memory-path story

### `host_payload/**`
- align bundled host payloads with the new host-vs-kernel split
- no payload should reintroduce host-level Brainstack behavior governance through stale files

### `tests/**` and proof/docs surfaces
- move verification to the new contract:
  - native explicit write first
  - Brainstack mirror second
  - no shadow authority regrowth
  - no mirror loop
  - explicit native-unavailable semantics

## execution order

1. Lock native host anchors
- confirm the native explicit-memory seam and `on_memory_write()` bridge as the primary explicit profile route

2. Lock authority precedence
- write down the native-first vs Brainstack-first truth classes before code changes

3. Lock one-way mirror contract
- define write identity, generation, and loop-prevention rules before any migration work

4. Demote Brainstack custom profile primacy
- start with:
  - `profile_contract.py`
  - `style_contract.py`
  - `behavior_policy.py`
  - `output_contract.py`
  - `control_plane.py`

5. Migrate current explicit state
- decide what current Brainstack-held profile/style truth:
  - moves to native host storage
  - remains archival
  - is superseded/tombstoned

6. Align parity surfaces
- README
- installer
- doctor
- host payload
- tests
- proof/docs

7. Preserve kernel retrieval and truth layers
- do not destabilize:
  - transcript
  - continuity
  - task truth
  - operating truth
  - graph / corpus

8. Rebuild mirror semantics
- ensure built-in host writes become the canonical explicit source
- ensure Brainstack mirrors and augments rather than competes

9. Prove product coherence
- explicit user fact write
- explicit preference write
- ordinary chat
- explicit rule recall
- post-reset recall
- no shadow authority regrowth from Brainstack-only extracted state
- no mirror loop or duplicate-native-write truth
- explicit native-unavailable behavior

## core decision

If a file currently does both:
- explicit profile authority
- memory-kernel augmentation

split the responsibility.

Native Hermes should keep explicit profile authority.
Brainstack should keep memory-kernel augmentation.
