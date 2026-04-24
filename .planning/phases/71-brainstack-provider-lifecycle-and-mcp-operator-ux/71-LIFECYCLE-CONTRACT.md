# Phase 71 Lifecycle Contract

## Scope

Brainstack exposes provider lifecycle status for Hermes/operator visibility.

This phase does not add a new daemon, scheduler, executor, or parallel host architecture.

## Lifecycle Status

`BrainstackMemoryProvider.lifecycle_status()` returns:

- provider status: `active`, `degraded`, or `unavailable`
- session id and principal scope key
- store initialization state
- Tier-2 worker state
- pending explicit write barrier count
- supported lifecycle hooks and their side-effect class
- exported provider tools
- operator-only tools
- disabled memory write-like tools
- shared-state safety rules

## Shared-State Rule

Optional MCP/operator access must use Brainstack APIs and provider/doctor surfaces.

Direct DB mutation is not an accepted operator path because it bypasses Brainstack authority, provenance, locking, and diagnostics.

## Hook Ownership

Hermes owns runtime lifecycle scheduling.

Brainstack owns memory/state/policy behavior inside provider hooks:

- `initialize`
- `system_prompt_block`
- `prefetch`
- `sync_turn`
- `on_pre_compress`
- `on_session_end`
- `shutdown`
- `get_tool_schemas`
- `handle_tool_call`

## Anti-Goals

- no Hermes rewrite
- no always-on Brainstack daemon
- no fake autonomy
- no direct DB operator write path
- no hidden degraded-state success
- no operator-only runtime status write silently exposed as a normal model-callable memory tool
