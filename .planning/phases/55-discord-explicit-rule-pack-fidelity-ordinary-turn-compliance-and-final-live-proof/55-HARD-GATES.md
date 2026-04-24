# Phase 55 Hard Gates

## hard gate 1. fresh-state definition

Every final proof run must start from explicitly defined fresh mutable state.

Must be reset between runs:
- session replay and session-local state
- mutable Brainstack/session caches that are not durable explicit truth
- gateway/session runtime residue

Must not be silently substituted or inferred:
- explicit durable truth after successful teaching
- proof artifacts from prior runs

## hard gate 2. explicit teaching capture

On Discord, after the user teaches:
- preferred name or addressing truth
- an explicit multi-rule pack

the product must capture both successfully without:
- asking for the same pack again immediately
- warning that memory may have failed
- relying on hidden transcript mining as the main capture path

## hard gate 3. same-session recall fidelity

Within the same Discord session:
- `how do you have to communicate`-style asks must return the full taught rule pack
- count must match the taught pack
- no rule may be omitted
- no rule may be inverted

Wording may vary.
Semantic coverage and integrity may not vary.

## hard gate 4. ordinary-turn compliance

After successful teaching, ordinary Discord turns must show compliance without extra prompting.

Required examples:
- greeting after teaching
- short factual reply
- direct name/addressing reply

Disallowed:
- warnings about missing rules
- re-asking for the rules
- handle-based greeting when explicit name truth exists
- decorative or stylistic drift that contradicts the stored pack

## hard gate 5. reset-safe durability

After session reset, the product must still:
- know the taught name/addressing truth
- know the full taught rule pack
- answer from that truth without warning or drift

## hard gate 6. contradiction/update safety

If the user corrects:
- the rule count
- a rule item
- the preferred name

the corrected truth must supersede the earlier version without:
- duplicate active truths
- mixed old/new recall
- semantic inversion in the recalled pack

## hard gate 7. zero user-surface leak

The following classes are automatic fail if they appear in ordinary Discord chat:
- rate-limit notices
- model-switch notices
- session reset notices
- token-usage summaries
- internal tool/progress traces
- internal fallback explanations

## hard gate 8. no benchmaxing / no heuristic sprawl

Implementation review must show:
- no benchmark-shaped tuning as the main fix
- no rule-pack-specific regex farms
- no locale- or punctuation-specific parser expansion
- no new Brainstack governor path

## hard gate 9. final Discord proof

The phase only closes when:
- the full Discord matrix is green once on fresh mutable state
- the full Discord matrix is green again on a second fresh mutable state run
- both runs are documented with pass/fail evidence

## required proof matrix

Each final Discord run must include:
- teach preferred name
- teach explicit multi-rule pack
- same-session recall of the full pack
- ordinary greeting after teaching
- direct name recall
- reset
- post-reset full-pack recall
- post-reset ordinary reply check
- optional correction/update check if the first run exposed versioning drift

