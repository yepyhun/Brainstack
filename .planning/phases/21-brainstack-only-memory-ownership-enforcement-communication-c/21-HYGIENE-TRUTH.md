# Phase 21 Memory Hygiene Truth

## Verified pollution

Persisted live state contains assistant self-explanations and internal-story artifacts such as:

- `Maintains persona.md and Humanizer SKILL.md for style consistency.`
- assistant style/source states referencing:
  - `Humanizer (SKILL.md)`
  - `Humanizer style from GitHub`
  - `persona_source`
  - `default_style`

These are not grounded user facts.

## Verified ingestion conclusion

This is not just one bad row.

The same failure class appears across:

- profile items
- graph states
- assistant self-explanations about memory behavior

That means the seam is reusable ingest/promotion logic, not one one-off transcript glitch.

## Adjacent similar failure

The same ingest family also shows temporal/data-quality drift:

- Laura injury date conflict surfaced with inconsistent year normalization

This confirms the manual audit was exposing a broader hygiene problem family, not a single wording bug.

## Repair decision

- harden normalization/reconciliation so assistant architecture speculation is not promoted as durable truth
- keep user facts and genuine user-requested behavioral rules admissible
- prefer class-based filtering and promotion rules
- verify that hygiene hardening does not amputate legitimate factual capture
