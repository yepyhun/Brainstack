# Phase 73 Maintenance Contract

## Scope

Phase 73 adds bounded, inspectable Brainstack memory maintenance.

It does not add hidden autonomy, a daemon, a scheduler, an executor, or unbounded dream/consolidation behavior.

## Tool Surface

`brainstack_consolidate` is enabled as a bounded maintenance tool.

Default mode is dry-run.

Apply mode is limited to:

- `semantic_index`

## Candidate Model

Dry-run reports candidates for:

- `semantic_index`: stale derived semantic evidence rows
- `profile_duplicate_content`: duplicate active profile category/content groups, review-only
- `graph_conflict_review`: open graph conflicts, review-only

Only `semantic_index` is apply-supported in this phase because it rebuilds derived index rows and does not delete durable truth.

## Receipt Rule

Every maintenance run returns a receipt with schema, mode, status, maintenance class, dry-run candidates, changes, and no-op/rejection reasons.

Unsupported apply classes return `rejected` and do not mutate state.

## Evidence Preservation

Apply mode must preserve durable truth rows.

The Phase 73 apply path may rebuild derived semantic evidence index rows, but it must not delete or rewrite profile, operating, task, corpus, continuity, transcript, or graph truth rows.

