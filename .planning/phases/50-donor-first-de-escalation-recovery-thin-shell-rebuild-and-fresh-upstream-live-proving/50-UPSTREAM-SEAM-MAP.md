# Phase 50 Upstream Seam Map

## baseline

- repo: `/home/lauratom/Asztal/ai/finafina`
- branch: `main`
- head: `2cdae233e2a869656b194baa9be0bc6eef6d988f`

## reading

Fresh upstream Hermes already has a generic memory-provider architecture.

That means the recovery should not start from:
- patching `run_agent.py` into a second memory brain
- rebuilding memory ownership in the host loop
- pushing behavior governance into generic host delivery

The correct simplification target is therefore:
- reduce host control
- preserve provider intelligence
- re-place “smartness” behind provider and memory-manager seams

It should start from the provider seams and keep the host thin.

## keep

These are good shell seams and should remain primary:

### `agent/memory_provider.py`
- keep as the canonical provider contract
- this is where donor-aligned memory behavior belongs
- Brainstack should fit here as one provider implementation or thin provider shell

### `agent/memory_manager.py`
- keep as the orchestration seam
- it already models:
  - provider registration
  - `system_prompt_block()`
  - `prefetch(query)`
  - `queue_prefetch(query)`
  - `sync_turn(user, assistant)`
  - `on_session_end(messages)`
- this is the right place for thin multi-provider coordination, not chat-governance logic

### `plugins/memory/*`
- keep as the main extension zone
- fresh upstream already expects memory behavior to live here
- this is the natural donor-first insertion surface

### `gateway/session.py`
- keep as generic session persistence and context tracking
- this is host infrastructure, not memory-kernel logic

### `tools/cronjob_tools.py`
- keep as host scheduling seam
- reminder delivery belongs to host scheduling
- memory may inform reminders, but should not absorb the scheduler

## thin-wire only

These may need changes, but only thin wiring changes:

### `run_agent.py`
- thin-wire only
- allowed role:
  - call memory manager hooks
  - inject memory context block
  - pass completed turns back to providers
- not allowed role:
  - become a Brainstack final-output rule engine
  - become the primary behavior-governance layer

### `gateway/run.py`
- thin-wire only
- allowed role:
  - delivery plumbing
  - lifecycle glue
  - startup/shutdown integration
- not allowed role:
  - memory policy engine
  - donor-specific behavior controller

### `hermes_cli/memory_setup.py`
- thin-wire only
- may be needed for provider activation / setup UX
- should not contain donor behavior logic

## remove or sharply reduce

These are the drift patterns the recovery should cut back:

### host-level hard output blocking
- remove as an ordinary-chat dependency
- if Brainstack validation remains at all, it must not be the central reply gate

### generic blocked fallback replies
- remove as a normal chat path
- examples like `Írd meg újra.` are product failures, not acceptable steady-state behavior

### host-side behavior governance
- sharply reduce
- the shell must not act like a second behavior engine over the donors

### reply-path dependence on memory compliance
- sharply reduce
- ordinary chat must still work even when memory-specific authority is incomplete or advisory

## executive reading

This phase should not be read as:
- make Brainstack dumber
- make donors weaker
- turn memory into passive storage

It should be read as:
- make the host thinner
- keep donors intelligent
- make the shell coordinate rather than govern

## execution implication

The first real code step in Phase 50 should not be “fix one more reply bug.”

It should be:
1. identify every place where host delivery depends on Brainstack output enforcement
2. remove or downgrade those dependencies
3. move any remaining memory-specific behavior back behind provider/memory-manager seams
4. prove the simpler product on a fresh runtime/profile baseline
