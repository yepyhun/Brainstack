# Phase 18 UAT

## Verdict

Phase 18 verify passes.

## User-facing verification outcome

### 1. Graph recall now surfaces connected facts more usefully

User verdict: `pass`

The user confirmed that the graph now helps bring back connected facts instead of only isolated one-off facts.

Accepted interpretation:

- when asking about one thing, the system should better surface related relations
- it should connect:
  - who works on what
  - what connects to what
  - what depends on what
- and it should do so in usable order rather than as a chaotic dump

### 2. Richer graph recall does not displace current truth

User verdict: `pass`

The user confirmed that the graph is richer without becoming more confusing:

- current explicit truth remains primary
- older or weaker graph material may still appear
- but it must not push down the current, stronger answer

### 3. Layer 2 usefulness is visible in ordinary conversation

User verdict: `pass`

This was called out as especially important by the user.

The accepted interpretation is:

- Phase 18 is not only a technical graph upgrade
- the improvement must show up in normal day-to-day questions too
- not only in obviously “graph-shaped” test prompts

## Technical proof

- targeted Phase 18 source-side validation passes
  - `26 passed`
- the new Kuzu path survived real regressions discovered during execution:
  - missing inferred object text
  - graph recall disappearing on inflected / punctuated query forms
  - one-way neighbor expansion being too weak for practical recall
- focused Phase 18 coverage now includes:
  - SQLite → Kuzu bootstrap
  - publish journal success/failure/replay behavior
  - richer Kuzu graph search behavior

## Runtime carry-through status

- source-side execution is complete
- Bestie carry-through is still blocked by target checkout permissions:
  - `hermes-config/bestie/config.yaml` is root-owned and unreadable from the current user
- because of that:
  - installer dry-run fails closed
  - real install also fails closed
- no rebuild was forced
- no push was performed

This permission block is not treated as a Phase 18 design failure. It is an environment-level carry-through blocker.

## What Phase 18 is considered to have proven

- Layer 2 now has a real embedded graph backend seam instead of relying on SQLite as the effective graph center
- the shell owns the first real cross-store publish journal
- graph usefulness is visibly stronger in normal recall
- L1 did not need to be redesigned again to benefit from the richer graph path

## What remains intentionally open

- full live carry-through once the Bestie config permission issue is fixed
- broader donor-strength recovery in later phases, especially once L3 is restored and the graph channel can work against the final multi-store shape
