# Phase 38 Context

## problem statement

The current operating substrate is real, but not fully trustworthy yet.

Two gaps remain:

- some operating record types still behave as if they were singleton truth even though the product surface treats them as plural lists
- the current write seam still depends too much on rigid structured blocks unless the user formats input very explicitly
- attempts to improve that seam can easily drift into heuristic sprawl if the boundary is not tightened first
- parts of the current read-time `prefetch` path still blur evidence lookup and write-side promotion

This is now a correctness and usefulness issue, not just a future polish idea.

## why this is the correct next phase

After `35`, the project gained first-class operating truth.

But the next live weakness is not only packet quality or style-contract sanitation.

It is that the operating substrate still:

- risks silent overwrite for plural truths
- and remains too rigid in what it can promote from ordinary chat
- while also keeping too much write-like behavior too close to read-time packet assembly

That blocks the second-brain goal more directly than another behavior-only refinement.

## accepted sharpened reading

- the project already has a valid operating-truth lane
- this phase is about making that lane semantically correct and more usable
- it must stay bounded and donor-friendly
- it must not turn into a broad heuristic planner or ontology project

## phase boundary

This phase is about:

- append-safe operating persistence
- bounded structure-promotion hygiene
- operating/task capture usefulness through existing donor-aligned seams
- read/write boundary cleanup for the operating/task promotion seam

This phase is not about:

- broad routing rewrite
- broad graph work
- packet-collapse replay
- autonomous planning behavior
- language-specific phrase harvesting

## expected proof shape

The proof should show:

- multiple commitments and next steps can coexist safely
- operating context can surface them without hidden overwrite
- structured capture still works
- some bounded structure-promotion cases improve without creating a heuristic intent layer
- read-time retrieval is cleaner and less mutation-shaped than before
- weak hints still do not overpromote into canonical truth

## canonical principle reference

- [IMMUTABLE-PRINCIPLES.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md)

## recommended model level

- `xhigh`
