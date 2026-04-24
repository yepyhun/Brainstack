# Phase 37 Context

## problem statement

The current Brainstack state has moved past the earlier ownership and packet-collapse bugs, but a new live blocker is now proven:

- the active canonical style contract can be polluted during capture and patch promotion
- the polluted canonical row can include user-speech framing and stale count/title language
- the compiled hot-path behavior policy can then rebuild itself from that polluted canonical contract
- after a session reset, the runtime faithfully recalls the wrong persisted authority

This is not merely a model hallucination and not merely an ordinary-turn packet issue.

The live audit now shows:

- active canonical contract revision stored under `preference:style_contract`
- title/content contaminated by a user prompt line
- stale `A set of 27 rules...` heading surviving after the user converged to `25`
- compiled policy title and clauses inheriting the same contamination
- dash-related punctuation semantics collapsing too aggressively in the hot path

That means the remaining failure is at the canonical capture and promotion seam.

## why this is the correct next phase

Phase `33` hardened personal truth and correction capture.

Phase `34` narrowed the behavior harness.

Phase `35` promoted first-class operating truth.

Phase `36` collapsed packet noise and overlapping hot-path renders.

None of those phases was primarily about this narrower but critical bug:

- can the style-contract lane preserve a clean canonical authority under real conversational correction flow
- and can reset behavior trust that authority

That is now the next correct phase because the current live failure is:

- reproducible
- architecturally localized
- user-visible
- and damaging to trust in reset-proof memory

## accepted sharpened reading

- the system did improve
- the reset was not itself the bug
- the bug is that reset exposed already-corrupted canonical truth
- the main failure is not style recall in general
- the main failure is:
  - polluted candidate generation
  - permissive parsing/promotion
  - missing first-class full replacement semantics
  - punctuation semantic collapse in compiler / validator handling
  - insufficient compiler guard
  - no clean recovery path for already-polluted principals

This phase should therefore fix the canonical contract seam itself, not add more runtime patching on top.

## phase boundary

This phase is about:

- style-contract candidate sanitation
- bounded multi-message rule-pack capture
- explicit canonical replace / supersede for full rule-pack replacement
- patch-lane hardening
- punctuation semantic fidelity for compiled and mechanically enforced style invariants
- polluted canonical-row quarantine or repair
- compiled-policy promotion safety for the style-contract surface
- reset-proof exact recall of the final user-authored contract

This phase is not about:

- broad behavior-policy redesign
- broad retrieval redesign
- packet collapse beyond the already-landed `36`
- new graph or operating-truth work
- user-specific hotfix rules
- transcript-first fallback as a substitute for fixing canonical truth

## expected proof shape

The proof should show:

- a conversational prompt line cannot become the canonical contract title
- stale count headings like `27 rules` cannot survive if the user explicitly converged to a newer final set
- explicit “this is the new final set” user intent can cleanly supersede the previous canonical pack
- bounded multi-message rule teaching still lands one clean canonical revision
- patch updates remain possible without carrying surrounding dialogue into canonical truth
- dash-related rules preserve their real semantic intent through compile + validate paths
- compiled hot-path policy no longer accepts polluted canonical source rows
- reset behavior recalls the cleaned final contract rather than older or contaminated truth

The most important proof is not just “cleaner parsing”.

It is:

- cleaner persisted authority
- cleaner compiled policy source
- trustworthy reset behavior
- and auditable repair for already-corrupted rows

## canonical principle reference

- [IMMUTABLE-PRINCIPLES.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md)

## recommended model level

- `xhigh`
