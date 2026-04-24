# Phase 70 Tool Surface Contract

## Scope

Phase 70 exposes a model-facing Brainstack memory tool surface through the provider boundary.

The accepted execution cut is read-only for memory truth:

- `brainstack_recall`
- `brainstack_inspect`
- `brainstack_stats`

`runtime_handoff_update` remains a scoped runtime status write from earlier runtime handoff work, but it is operator-only by default and is not exported through the normal model-callable memory tool surface.

It is not a memory capture, supersession, or invalidation surface.

## Disabled Until Phase 72

The following memory write-like tools are not exported as model-callable schemas and return an explicit disabled error if called:

- `brainstack_remember`
- `brainstack_supersede`
- `brainstack_invalidate`
- `brainstack_consolidate`

Reason: explicit durable capture, supersession, invalidation, and consolidation contracts are not frozen until later phases.

## Evidence Contract

Every read-only memory tool response must be evidence-backed and scoped.

- `brainstack_recall` returns selected evidence, channel status, routing, evidence count, and bounded packet preview.
- `brainstack_inspect` returns the full query inspect report.
- `brainstack_stats` wraps the Phase 65 memory-kernel doctor report.

No tool may read raw DB state directly into the model outside Brainstack's bounded diagnostic/reporting surfaces.

## Anti-Goals

- no scheduler, executor, or approval-governor tool
- no unscoped durable writes
- no hidden repair side effect
- no write-like memory tool before Phase 72
- no operator/debug-only mutation exposed as a normal memory recall tool
- no runtime status write exposed as model-callable unless explicitly configured by the runtime owner
