# Phase 59 Context-Window Attribution

## Verified current host-side prompt contributors

- `MEMORY_GUIDANCE ~4597 char`
- `USER_PROFILE_GUIDANCE ~3248 char`
- `TOOL_USE_ENFORCEMENT_GUIDANCE ~1419 char`
- `OPENAI_MODEL_EXECUTION_GUIDANCE ~3176 char` when active
- live `USER.md ~790 char`

These sit alongside:

- builtin memory block
- builtin user-profile surfaces
- tool schema overhead
- conversation history
- Brainstack system-prompt block
- Brainstack per-turn prefetch packet

## Accepted attribution verdict

- rapid context growth is not truthfully attributable to Brainstack alone
- Brainstack still contributes through:
  - provider system-prompt projection
  - per-turn working-memory packetization
- the right correction is therefore:
  - attribution first
  - then bounded Brainstack-owned allocation/ranking work
- the wrong correction would have been:
  - blame-first
  - shelf deletion
  - backend swap theater
  - benchmark-only trimming
