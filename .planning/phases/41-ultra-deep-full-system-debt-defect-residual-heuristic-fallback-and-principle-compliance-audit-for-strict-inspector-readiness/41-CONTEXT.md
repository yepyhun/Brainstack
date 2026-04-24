# Phase 41 Context

## problem statement

The product is stronger after phases `36` through `40.3`, but it is not yet honest to call it fully inspector-proof or fully “as intended” everywhere.

The next strict need is a full-system audit that captures everything still open, including issues that are not in the currently known residual list.

## why this phase exists

- the upcoming reviewer is expected to attack:
  - architecture seams
  - heuristic drift
  - fail-open behavior
  - fallback truth divergence
  - token waste
  - spaghetti or hidden coupling
  - runtime drifts that undermine claims of correctness
- recent fixes proved that some issues are only obvious when source, deploy, and live runtime are examined together
- therefore the next correct step is not optimistic shipping language, but a hard debt inventory

## initial proven findings entering the phase

### runtime finding 1

- Discord slash command sync failure:
  - `In group 'skill'`
  - `Command exceeds maximum size (8000)`
- accepted reading:
  - the previous Discord `/skill` representation was structurally wrong for Discord payload limits
  - this is now fixed, but it remains an important audit data point because it was a live deploy issue, not just a hypothetical one

### runtime finding 2

- Brainstack route-resolution and auxiliary memory flows showed OpenRouter `402` failures
- accepted reading:
  - this is a real runtime limitation and product-risk surface
  - it must be split carefully into:
    - economic/provider drift
    - fail-open or fallback behavior quality
    - whether the product still behaves truthfully under that failure

### runtime finding 3

- Hermes auth/runtime warned that the configured CA bundle path did not exist and default certificates were used instead
- accepted reading:
  - this is environment or deploy drift
  - it is not necessarily a product logic bug
  - but a strict inspector will still count it as operational debt unless clearly classified

## audit posture

- truth-first
- no debt laundering
- no “probably fine” language
- no principle reinterpretation

## canonical principle reference

- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`

## recommended model level

- `xhigh`
