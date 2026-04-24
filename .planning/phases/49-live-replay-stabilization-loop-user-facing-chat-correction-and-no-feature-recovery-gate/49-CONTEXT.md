# Phase 49 Context

## why this phase exists

The recent live Bestie incidents show that local kernel correctness and green slice tests are no longer enough as the main quality signal.

The user-facing product still fails in ways that make the whole system feel worse:
- internal Brainstack blocker text can reach the user
- internal tool progress can reach the user
- natural rule-recall questions can still miss style authority
- transcript persistence has failed on the live host path
- reminder scheduling can still be experienced as incorrect in ordinary chat

The accepted reading is that the product has suffered from cross-layer sequencing drift:
- source correctness improved
- host/runtime seams were fixed later or separately
- live authority and live UX did not always converge with the code at the same time

This phase corrects that by switching to one closed replay-and-correction loop on real chat failures.

## incident classes this phase must close

1. blocked-output leak
- user saw: `Brainstack output blocked because the reply breaks an active communication rule. Please regenerate the answer in compliant form.`
- this is not acceptable fail-closed behavior
- it is an internal enforcement leak

2. tool-trace leak
- user previously saw `session_search`, `cronjob`, and interrupt/progress traces in ordinary chat
- these are operator/debug surfaces, not user-facing chat content

3. style recall miss
- natural questions like `miért nem tartod be a szabályokat?` or `emlékszel a 25 szabályra?` must resolve to style authority on the live path
- this must not degrade into transcript panic or missing-memory behavior

4. transcript continuity instability
- if transcript persistence fails on the host path, continuity-backed recovery becomes untrustworthy

5. scheduling correctness instability
- reminder delivery must be correct on the real user-facing path, not only on internal timestamps

## why this is not benchmark work

This phase does not optimize for one synthetic metric or one hand-picked wording.

It uses a bounded pack of real failing chats as a product-recovery gate:
- the tests are replay-driven
- the fixes must generalize across the whole replay pack
- no new capability work is allowed to bypass the gate

## expected execution style

- small bounded correction batches
- replay after every batch
- no feature growth during the phase
- no heuristic sprawl
- no local pass accepted as phase success if the docker/live replay pack still fails
