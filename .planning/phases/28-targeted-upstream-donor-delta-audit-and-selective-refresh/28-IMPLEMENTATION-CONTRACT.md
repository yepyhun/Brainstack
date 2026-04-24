# Phase 28 Implementation Contract

## Objective

Execute a bounded, donor-first upstream delta audit and selective refresh over the latest Hindsight, MemPalace, and Graphiti state, while refusing blanket sync, donor-transplant drift, or low-value maintenance burden.

## System doctrine this phase must preserve

- Brainstack remains the only durable memory owner
- Brainstack remains the implementation source of truth
- donor-first means:
  - compare against upstream honestly
  - adopt thin useful deltas where justified
  - refuse broad transplant when not justified
- updateability matters as much as capability
- no ordinary-turn token regression is acceptable without explicit payoff
- Bestie is not a parallel implementation target in this phase

## Workstream A: Latest-delta truth matrix

- produce one donor-by-donor matrix covering:
  - latest upstream head
  - latest relevant runtime delta
  - current local overlap
  - portability
  - expected ROI
  - final decision

## Workstream B: Hindsight selective candidate audit

- audit whether latest recall-budget discipline is already covered locally
- if not covered, design the thinnest Brainstack-owned adaptation that:
  - uses current route/packet logic
  - does not create a new product-shaped config forest
  - improves bounded retrieval behavior
- if already covered, close as no-op

## Workstream C: MemPalace boundary audit

- prove whether direct Chroma usage is fully confined to the backend seam
- if leakage exists, collapse it behind the existing backend contract
- if leakage does not exist, close with proof only
- do not use this workstream to smuggle in corpus feature expansion

## Workstream D: Graphiti adopt-now gate

- check only for concrete immediate runtime-ROI deltas
- if no such delta exists, close Graphiti as explicit no-op for this phase
- do not broaden into L2 redesign or graph capability ideation here

## Workstream E: Donor refresh truth

- align donor registry / refresh reporting / docs with the actual current adoption reading if the audit changes it
- do not over-claim donor freshness or compatibility

## Protected boundaries

### Anti-overengineering boundary

- no blanket sync
- no new donor runtime dependency
- no broad host refactor
- no second retrieval engine
- no new abstraction layer unless it removes more local glue than it adds

### Donor-first boundary

- use donor deltas to sharpen local truth, not to justify random rewrites
- if the donor slice cannot be adopted thinly, it should usually be deferred
- if the donor slice only duplicates current local behavior, it should not land

### Product-value boundary

- every adopted slice must defend itself through one of:
  - better bounded retrieval discipline
  - lower maintenance risk
  - clearer operational auditability
  - cleaner donor refresh truth
- “upstream changed” is not enough

### Mirror boundary

- no Bestie-side code changes in this phase
- if a slice lands, mirroring is a later follow-up phase

## Minimum evidence required before calling Phase 28 done

- an explicit donor-delta matrix exists
- Hindsight has a shipped-or-no-op verdict
- MemPalace has a shipped-or-no-op verdict
- Graphiti has a shipped-or-deferred verdict
- any landed code is thin, local, and donor-first
- bounded verification proves no obvious packet/token regression
- donor refresh truth is updated if needed
