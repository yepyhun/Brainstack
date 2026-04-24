# phase 29 implementation contract

## objective

Restore planning discipline around the live communication-contract regression so execute must produce a hard seam verdict instead of another fuzzy "it forgot" story.

## system doctrine this phase must preserve

- Brainstack remains the single owner of personal memory on this axis
- live deployed behavior outranks paper architecture for the next decision
- the project must preserve donor-first updateability and avoid one-off local glue unless the proven seam requires it
- this phase must deliver a hard verdict, not a vague "better than before" conclusion

## non-negotiables

- no persona-file or notes-file fallback
- no skill-file storage workaround for personal communication rules
- no network or local-search substitute presented as memory
- no donor sync detour unless the forensic trace proves the donor seam is causal
- no prompt-strength story accepted by itself

## workstream a: live failing-trace truth

- reproduce one accepted post-reset failure on the deployed path
- ensure the trace shows:
  - identity surviving
  - Humanizer / communication contract failing
  - wrong fallback behavior appearing

## workstream b: durable-state vs retrieval split

- compare durable identity truth and durable style-rule truth for the same principal
- then compare retrieved identity truth and retrieved style-rule truth for the same failing path
- do not blur durable-state absence with retrieval absence

## workstream c: contract-assembly vs application split

- inspect how the active communication contract is assembled
- inspect whether the final runtime input still carries it with the right precedence
- keep assembly failure and application failure separate

## workstream d: stale-runtime falsification

- prove whether the deployed reset/runtime/config path matches the current source-of-truth
- if not, stop logic patching and fix runtime parity first

## workstream e: verdict and repair surface

- end with one seam verdict
- define the smallest correct repair surface
- define the explicit no-touch zones for the repair

## proof standard

Every conclusion in this phase must be tagged as one of:

- live runtime evidence
- stored-state evidence
- retrieval/assembly evidence
- inferred but not yet proven

## acceptable outputs

- a proven failing seam and a repair-ready execute path
- a falsified user theory with a better proven seam
- an explicit runtime-parity finding that blocks code changes until deployment is corrected

## unacceptable outputs

- \"it probably forgot\"
- \"the prompt was weak\"
- \"let's just hardcode the style rules\"
- any fix that restores style recall by creating a second owner for personal memory

## protected boundaries

### anti-band-aid boundary

- do not solve this with persona files, skill files, or ad hoc prompt stuffing

### ownership boundary

- no repair may make personal style truth authoritative anywhere outside Brainstack

### runtime-parity boundary

- no Brainstack logic change is valid if the deployed target is proven stale or miswired

### truth boundary

- the final verdict must say what was ruled out, not only what is suspected

## minimum evidence required before calling phase 29 done

- one accepted live failing trace
- one stored-state comparison for identity vs style truth
- one retrieval/assembly trace for the same failure path
- one explicit verdict naming the seam and ruling out at least the adjacent seams
- one bounded repair direction or explicit runtime-parity block

## final seam status

- proven primary seam:
  - scoped retrieval / contract compatibility was dropping legacy unscoped communication-preference rows
- proven secondary correctness bug:
  - Tier-2 worker and session-end flush could fail before promotion because the Tier-2 caller passed `response_format` into a `call_llm()` signature that does not accept it
- shipped repair shape:
  - open-time deterministic backfill from transcript-derived unique principal scope for legacy unscoped principal-scoped profile rows
  - Tier-2 caller argument fix via `extra_body`
- runtime proof:
  - after repair, the deployed docker runtime rebuilds the full communication contract for the affected principal on fresh `AIAgent` startup
  - after repair, runtime `on_session_end()` can again land a scoped preference row end-to-end
- ruled out:
  - "the data was never stored at all"
  - "the model ignored a correct final contract that was already present"
  - "prompt hardening by itself would solve the regression"
- explicitly not accepted as the minimum repair target:
  - principal-model drift between older `default/hermes/numeric-id` scope and the newer expected naming shape

## phase 29 done means

- the regression has one named seam verdict
- the smallest correct repair surface was implemented without creating a second owner for personal memory
- the deployed docker target shows repaired contract recovery on fresh startup
- the next remaining proof obligation is external UAT, not more internal guesswork

## recommended model level

- `xhigh`
- this phase must be executed with enough reasoning depth to separate:
  - durable-write failure
  - retrieval failure
  - contract-assembly failure
  - application/override failure
  - stale deployed-runtime failure
