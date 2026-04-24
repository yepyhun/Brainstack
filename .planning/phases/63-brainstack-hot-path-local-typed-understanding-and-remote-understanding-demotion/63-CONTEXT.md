# Phase 63 Context

## why this phase exists

Phase `61.1` contained the availability damage from remote `structured_understanding`.
Phase `62` restored authoritative live-state truth for the current scheduler state.
Neither phase removed the deeper architectural defect: ordinary Brainstack task/operating behavior still places too much authority on a remote semantic-understanding seam.

## current live facts

### 1. the remote seam is bounded, not removed

- Phase `61.1` introduced explicit degraded behavior and bounded failure caching
- the accepted residual after Phase `61.1` was:
  - `control_plane` still performs one structured query-understanding call for ordinary packet analysis

### 2. live-state authority is now separated correctly

- Phase `62` added `live_system_state` as typed operating truth
- this solved the specific "is it actually live now?" authority defect for the scheduler-backed path
- it did not solve ordinary task/operating hot-path routing or capture

### 3. remote-understanding failures are real production evidence

- recent live evidence showed timeouts, invalid payloads, and provider/credit failures in and around remote-understanding calls
- the problem is therefore not theoretical maintainability debt
- it is an actual hot-path correctness and availability risk

### 4. the project cannot recover by restoring heuristic routing

- the governing rule is explicit:
  - code-level heuristics, cue lists, phrase farms, and locale-specific routing are not an acceptable fallback architecture
- therefore "just restore the old simple routing" is not a valid answer

### 5. naive local rules are still a trap

- a local deterministic layer is only acceptable if it is genuinely typed and substrate-driven
- renaming cue tables as "patterns" or "rules" would still violate the same architectural principle

### 6. multimodal is a real constraint, not decoration

- the user requirement is not merely "remove Hungarian phrases"
- the kernel must remain viable for future non-text or mixed-modality event shapes
- therefore a text-only intent detector is not an acceptable long-term replacement for the remote seam

## current generalized defect statement

The ordinary Brainstack kernel still delegates too much route/capture authority to a remote semantic-understanding seam where it should instead rely on local typed authoritative substrates. Phase `61.1` made that dependence less explosive; it did not make it structurally correct.

## why this is Brainstack-owned

- the defect sits in Brainstack route/capture authority, not in generic Hermes runtime behavior
- the needed correction is about:
  - what Brainstack considers authoritative input
  - how Brainstack determines ordinary read/capture classes
  - how Brainstack separates hot-path authority from optional enrichment
- generic cron/tool/provider cleanup may still exist elsewhere, but it is not the owner of this defect

## why Phase 61.1 and Phase 62 are not enough

- Phase `61.1` answered:
  - how Brainstack should fail more safely when remote understanding goes bad
- Phase `62` answered:
  - how Brainstack should represent current live scheduler-backed state as typed authority
- Phase `63` must answer:
  - how the ordinary kernel stops needing remote semantic classification as the primary decision-maker for task/operating behavior

## what the next execution must decide

### 1. what the local typed substrate actually is

- which normalized inputs are allowed
- which are authoritative versus merely supportive

### 2. how ordinary read routes are decided locally

- task lookup
- operating lookup
- current-work lookup
- recap/current-state separation

### 3. how ordinary capture eligibility is decided locally

- task capture
- operating-truth capture
- when the answer is correctly "do not capture"

### 4. what remains off-path

- which model-based or remote understanding steps, if any, still remain
- why those remaining uses no longer carry hot-path authority

### 5. how multimodal compatibility is preserved

- how the chosen local structure avoids text-only architectural lock-in

## non-goals to reject

- generic Hermes cleanup disguised as kernel work
- prompt-only band-aids presented as architectural correction
- a shadow classifier in the host/runtime layer
- a hidden reintroduction of phrase farms under different names
- a "works for this Discord thread" rescue design

## source-of-truth rule

- this phase must plan from the actual Brainstack source and the validated Phase `61.1`/`62` outcomes
- external commentary may help pressure-test the plan, but it does not outrank the code or the validated residuals
