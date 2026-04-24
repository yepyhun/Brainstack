# Phase 21 Summary

Status: execution-complete at gate

## What changed

- Closed the deepest live ownership seam by making `flush_memories` request structured JSON output on the real deployed provider path instead of relying on unconstrained reasoning-only completions.
- Hardened Tier-2 parsing so embedded / wrapped JSON still recovers cleanly instead of silently collapsing profile extraction.
- Replaced fuzzy graph search as the primary communication-contract source with direct current-state/profile retrieval for the active contract path.
- Fixed the contract subject model so user-owned communication preferences and assistant naming rules both participate in the active contract.
- Tightened the contract renderer so known communication slots render as explicit non-optional behavior rules rather than weak raw snippets.
- Added transcript-derived communication-slot backfill for explicit user rules that the live extractor can omit when it bundles or under-emits narrow formatting constraints.
- Preserved Brainstack-only ownership by keeping personal memory off file/skill/tool detours and filtering assistant self-explanation / prompt-mechanics pollution out of durable truth.

## Files touched

- Brainstack source:
  - `brainstack/tier2_extractor.py`
  - `brainstack/retrieval.py`
  - `brainstack/db.py`
  - `brainstack/reconciler.py`
  - `tests/test_brainstack_phase21_memory_ownership.py`
- Bestie runtime:
  - `agent/auxiliary_client.py`
  - `agent/brainstack_mode.py`
  - `run_agent.py`
  - `plugins/memory/brainstack/tier2_extractor.py`
  - `plugins/memory/brainstack/retrieval.py`
  - `plugins/memory/brainstack/db.py`
  - `plugins/memory/brainstack/reconciler.py`
  - `tests/agent/test_auxiliary_client.py`
  - `tests/run_agent/test_brainstack_only_mode.py`

## Validation

- Brainstack Phase 21 source slice:
  - `10 passed`
- Bestie Brainstack-only ownership slice:
  - `9 passed`
- Bestie auxiliary structured-response / flush routing sanity slice:
  - `4 passed`
- code-quality spot checks on the owned Phase 21 slices:
  - Brainstack source `ruff`: clean
  - Brainstack source `mypy`: clean
  - Bestie Brainstack mirror + `agent/brainstack_mode.py` `ruff`: clean
  - Bestie Brainstack mirror + `agent/brainstack_mode.py` `mypy`: clean
  - Bestie `agent/auxiliary_client.py` + `tests/agent/test_auxiliary_client.py` `ruff`: clean
- strict deployed-path live proof:
  - `reports/phase21/brainstack-phase21-live-rerun-strict.json`
  - clean temp `HERMES_HOME` seeded from deployed config/auth
  - actual deployed model path:
    - `provider: nous`
    - `model: xiaomi/mimo-v2-pro`
  - verdict:
    - `owns_personal_memory_axis = true`
  - persisted contract truth now includes:
    - `preference:response_language`
    - `preference:ai_name`
    - `preference:communication_style`
    - `preference:emoji_usage`
    - `preference:message_structure`
    - `preference:pronoun_capitalization`
    - `preference:dash_usage`
  - behavior proof after reset:
    - recalls `Tomi`
    - recalls `Bestie`
    - recalls Hungarian response requirement
    - avoids internal file / skill / memory-mechanics claims
    - avoids emoji use
    - maintains multi-thought newline structure
    - maintains `Én / Te / Ő` capitalization under a non-casing-led probe
  - current-state representation audit:
    - `current_state_pairs = []`
    - treated as non-blocking representation truth because profile rows, injected contract, and post-reset behavior still align on the owned communication contract

## Honest reading

- The earlier manual problem was real and multi-layered:
  - structured extraction on the live provider path was incomplete
  - the communication contract was assembled from brittle evidence sources
  - narrow style rules could be lost even when the main preference bundle survived
  - assistant self-explanations could pollute durable truth
- The final fix is not a `persona.md` band-aid.
- The durable owner on this axis is now Brainstack:
  - clean home
  - Brainstack-only memory mode
  - no side skill/persona file dependency required for the proof
- The architectural boundary is now clearer:
  - Brainstack owns the personal-memory axis
  - native host capabilities are still allowed outside that axis
  - the fix closed competing persistence/retrieval channels instead of trying to replace every native feature
- Residual host dependency is now limited to `SOUL.md` as a compatibility shell, not as the owner of personal style / identity memory.
- Full-file lint/type cleanliness for the host monolith is not claimed here.
  - `run_agent.py` and the broader `agent/auxiliary_client.py` file still carry pre-existing host baseline lint/type noise outside the owned Phase 21 slices.
  - Phase 21 only claims green quality gates on the owned source/mirror slices and the touched auxiliary sanity file.

## Carry-forward note

- A stricter adjacent-similar pass reproduced and then closed two sibling detour classes at the shared ownership guard seam:
  - `cronjob` being used as automation-based personal-memory storage
  - `execute_code` calling secondary-memory APIs like `plur_learn`
- The final green strict reruns showed:
  - no memory-detour tool calls
  - no automation detours
  - no secondary-memory API detours
- This strengthened the architectural reading:
  - the right boundary is axis-specific Brainstack ownership, not total native-feature displacement

## Next step

- Checkpoint Phase 21.
- If continuing immediately, prefer broader deployed-live conversational quality / coverage validation over another personal-memory micro-phase.

## Recommended effort

- `high`
