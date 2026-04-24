# Phase 72 Explicit Durable Capture Contract

## Scope

Phase 72 enables explicit durable writes through typed Brainstack tool payloads.

It does not reintroduce Tier-1 keyword farms, language-specific cue lists, implicit live capture, scheduler behavior, executor behavior, or approval governance.

## Enabled Tool Surface

The following tools are model-callable after this phase:

- `brainstack_remember`
- `brainstack_supersede`

The following remain disabled:

- `brainstack_invalidate`
- `brainstack_consolidate`

Current state after Phase 73: `brainstack_consolidate` is enabled only as bounded maintenance. `brainstack_invalidate` remains disabled.

## Explicitness Rule

Durable capture is accepted only from a schema payload with:

- `shelf`
- `stable_key`
- `source_role`
- shelf-specific required fields

Allowed shelves:

- `profile`
- `operating`
- `task`

Allowed source roles:

- `user`
- `operator`

Assistant-authored, tool-authored, system-authored, or reflection-generated payloads are rejected before durable truth promotion.

## Shelf Rules

Profile capture requires:

- `category`
- `content`
- optional numeric `confidence`

Operating capture requires:

- `record_type` from Brainstack operating record types
- `content`

Task capture requires:

- `title` or `content`
- optional `due_date`, `date_scope`, `status`, and `optional`

## Supersession Rule

`brainstack_supersede` writes through the same stable-key upsert path and records `supersedes_stable_key` in metadata/receipt.

This makes newer truth win without duplicate truth spam.

## Receipts

Every accepted or rejected capture returns a receipt.

Rejected receipts include structured error codes and do not write durable truth.

Committed receipts include:

- schema
- tool name
- operation
- shelf
- stable key
- principal scope key
- source role
- authority class
- content hash
- content excerpt
- supersession pointer when applicable

## Multilingual Rule

Multilingual support comes from typed schema payloads, not phrase matching. Hungarian, English, German, Chinese, or other language content is accepted when the same schema fields are present.
