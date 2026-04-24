# Phase 21 Ownership Truth

## Verified runtime truth

- deployed config runs in Brainstack-only mode:
  - `memory.provider: brainstack`
  - `memory.memory_enabled: false`
  - `memory.user_profile_enabled: false`
- legacy `memory` and `session_search` are already hidden/blocked in Brainstack-only mode
- host runtime still loads `SOUL.md` as identity/context input unless context files are skipped
- Brainstack still injects its own system prompt block through the memory manager

## Verified shadow-path truth

- the live runtime still allowed personal-memory detours through non-legacy tools
- current `blocked_brainstack_only_tool_error()` only blocks:
  - legacy `memory` / `session_search`
  - `skill_manage` writes with personal-memory markers
  - file tools only for:
    - `~/.hermes/notes/`
    - `MEMORY.md`
    - `USER.md`
- it does not currently cover the observed side-write class around:
  - `persona.md`
  - `/root/.hermes` personal-memory fallback files
  - code-based personal-memory writes
- adjacent-similar reproduction closed two sibling detour classes at the shared guard layer:
  - `cronjob` used as automation-based personal-memory storage
  - `execute_code` calling secondary-memory APIs like `plur_learn`

## Important ownership conclusion

The ownership breach is real, but it is not a proof that host persona files are the intended owner.

The real problem is:

- Brainstack is the intended owner
- host compatibility shell still exists
- the guard layer is too narrow, so the model can still improvise a second personal-memory path
- the correct architectural response is axis-specific ownership, not blanket native-feature displacement
- native host capabilities like scheduling remain legitimate outside this axis; what must be blocked is their use as a second persistence/retrieval channel for personal-memory truth

## Repair decision

- repair the shared Brainstack-only ownership guard
- do not create a new owner
- do not make `persona.md` stronger
- preserve host compatibility inputs only as bounded shell, not as mutable personal-memory source
- keep useful native host capabilities intact outside the personal-memory axis
