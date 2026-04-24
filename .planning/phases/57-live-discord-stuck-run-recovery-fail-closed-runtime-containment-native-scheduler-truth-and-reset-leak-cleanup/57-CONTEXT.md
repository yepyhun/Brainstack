# Phase 57 Context

## why this phase exists

Phase 56 cleaned up deployed explicit-truth state and authority residue, but the installed Discord runtime still shows a separate live correctness defect family:

- an ordinary user turn can hang until manual `/reset`
- Brainstack provider initialization can fail with `std::bad_alloc`
- graph publish/search paths can remain half-open with repeated `KuzuGraphBackend is not open`
- reset lifecycle text can still leak to the user
- reminder acknowledgements are not yet trustworthy enough to prove native scheduler truth

This is no longer a memory-design phase.
It is live-runtime correctness and containment work on the installed product.

## verified live-state evidence

Accepted evidence from the live Discord run and runtime logs:

- user asked:
  - `Mondj 3 budapesti hidat.`
- runtime recorded the inbound turn
- no `response ready` followed for that turn
- the hanging run was only cleared after manual `/reset`

Same runtime window also showed:

- `Memory provider 'brainstack' initialize failed: std::bad_alloc`
- repeated `Brainstack graph search failed; falling back to SQLite: KuzuGraphBackend is not open`
- user-facing bare `Session reset.`

Separate live UI evidence also showed a scheduler-truth defect:

- the bot could acknowledge a reminder / cronjob as if it were created
- but the requested near-term reminder did not arrive
- therefore the product cannot yet claim reminder success truthfully

## accepted diagnosis

The remaining defect family must be described carefully:

- it is not proven yet as a pure Brainstack-only bug
- it is not safe to dismiss as provider-only noise either

The accepted diagnosis is:

- the installed runtime still has a correctness hole spanning:
  - run-management / stuck-turn handling
  - provider or auxiliary-call completion boundaries
  - Brainstack provider initialization containment
  - graph backend half-open residue
  - scheduler truthfulness
  - reset surface hygiene

This phase must separate:

- root cause
- containment
- user-surface truthfulness

without heuristic drift.

## source-of-truth rule for this phase

- code source of truth:
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`
- install-and-proof target:
  - `/home/lauratom/Asztal/ai/finafina`

If a fix cannot be reproduced onto the installed runtime from the source-of-truth repo, it does not count.

## proof stratification

This phase still treats proof in layers:

1. installed runtime / provider-path proof
2. real Discord UI proof

Neither substitutes for the other.

This phase also adds one more necessary distinction:

3. scheduler delivery proof

A claimed reminder is not proven until it actually exists in the native scheduler and fires.

## design guardrails

- do not reintroduce Brainstack behavior governance
- do not solve the current example with user-specific or Hungarian-specific handling
- do not patch surface wording only while the underlying stuck-run defect remains
- do not accept half-open graph/provider state as “good enough because SQLite fallback exists”
- do not accept reminder success claims without real native scheduler evidence

## anti-drift reminders

- do not turn the memory kernel into a scheduler truth engine
- do not turn the host into a new rule-governor layer
- do not solve the hang with a cosmetic timeout message while the run still remains unmanaged underneath
- do not leave `finafina` hand-fixed in a way the source installer cannot reproduce
