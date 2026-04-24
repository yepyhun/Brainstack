# Phase 57 Hard Gates

## hard gate 1: source-of-truth discipline

- only `/home/lauratom/Asztal/ai/atado/Brainstack-phase50` is edited for the fix
- `finafina` only receives install/copy/rebuild output from the source-of-truth repo
- if a needed runtime correction cannot be reproduced from source of truth, the phase fails

## hard gate 2: no silent stuck ordinary turn

- on the installed Discord runtime, an ordinary user question must not hang indefinitely waiting for manual `/reset`
- the tested turn must end as one of:
  - normal response
  - bounded, truthful failure surfaced to the user
- a silent stall that only clears after `/reset` is automatic fail

## hard gate 3: fail-closed provider and graph containment

- `std::bad_alloc` or comparable provider-init failure must not leave a misleading half-alive memory lane
- graph backend unavailability must not keep producing active request-path `KuzuGraphBackend is not open` churn
- fallback behavior must be stable and bounded, not half-open

## hard gate 4: scheduler truth

- when the bot says a reminder / cronjob was created, a real native scheduled job must exist
- a short-horizon same-day reminder proof must show actual delivery
- if native scheduler creation fails, the bot must not claim success

## hard gate 5: reset surface hygiene

- bare `Session reset.` is automatic fail in ordinary user-facing Discord chat
- lifecycle/status text must stay out of ordinary conversational messages

## hard gate 6: installed-runtime proof

- the fix is installed into `finafina` from `Brainstack-phase50`
- the installed runtime is rebuilt
- the observed runtime is the installed latest source-of-truth state

## hard gate 7: final real Discord UI proof

- the final proof is executed on the installed `finafina` runtime
- it includes:
  - one ordinary-turn response after prior memory/scheduler activity
  - one reminder creation proof
  - one reminder delivery proof
  - one reset-boundary cleanliness check
- no hand-patched-only state may be relied on

## hard gate 8: no false closure

- the phase cannot be called complete because `/reset` recovers the session
- the phase cannot be called complete because SQLite fallback exists while graph/provider paths remain half-open
- the phase cannot be called complete because the bot can verbally restate reminder data even if native scheduler delivery failed
