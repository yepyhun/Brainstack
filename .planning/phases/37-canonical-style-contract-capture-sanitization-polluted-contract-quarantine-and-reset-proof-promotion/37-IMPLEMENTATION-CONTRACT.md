# Phase 37 Implementation Contract

## invariant

Brainstack must persist and promote a clean canonical style contract that survives reset without carrying conversational framing, stale headings, or polluted rule text into the authoritative memory lane.

## required implementation properties

- canonical style-contract promotion must accept only structurally clean contract content
- user-speech framing, turn prefixes, debugging prompts, and similar conversational scaffolding must not become:
  - canonical contract title
  - canonical section heading
  - canonical rule line
  - compiled hot-path clause text
- multi-message explicit rule teaching may remain, but it must pass through bounded contract extraction rather than raw fragment concatenation
- full canonical pack replacement must have a first-class replace / supersede operation
- patch mode must remain narrow:
  - short patch-like inputs only
  - rule-replacement semantics only
  - no backdoor full-contract promotion
- dash-related punctuation invariants must preserve semantic distinction across:
  - canonical truth
  - compiler projection
  - mechanical repair
- compiled behavior policy must reject or quarantine polluted canonical source rows instead of normalizing them into active hot-path guidance
- already-polluted canonical rows must have an auditable repair or quarantine path
- exact style-contract recall must remain available once canonical truth is clean
- the result must remain donor-first, upstream-friendly, and free of new heuristic farms

## prohibited outcomes

- new user-specific deny lists
- broad cue-farm parsing for every chat message
- silently deleting canonical state without an auditable recovery path
- preserving polluted canonical rows while only masking them at render time
- collapsing distinct punctuation rules into one generic dash policy
- breaking legitimate multi-message explicit rule teaching in order to avoid the bug
- hiding remaining corruption behind prompt-time overrides

## likely implementation seams

- `brainstack/style_contract.py`
- `brainstack/__init__.py`
- `brainstack/db.py` only if needed for repair or quarantine support
- `brainstack/behavior_policy.py`
- `brainstack/retrieval.py` only if compiled policy promotion or recall trace needs canonical cleanliness gating
- the minimal `hermes-final` seams needed to preserve parity if runtime install behavior depends on these paths

## verify contract

- prove polluted conversational prefixes cannot become the canonical title
- prove stale rule-count headings cannot survive explicit final convergence to a new set
- prove explicit full-pack replacement cleanly supersedes the old canonical pack
- prove bounded multi-message rule teaching still lands a clean canonical revision
- prove patch mode rejects conversational framing and only performs bounded rule replacement
- prove dash-related rules keep their true semantics through compile + validate
- prove compiled hot-path policy refuses polluted canonical source rows
- prove already-polluted live rows can be repaired or quarantined safely
- prove parity on:
  - source
  - `hermes-final`
  - rebuilt live runtime
- prove reset after commit recalls the cleaned final contract exactly

## canonical principle reference

- [IMMUTABLE-PRINCIPLES.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md)

## recommended model level

- `xhigh`
