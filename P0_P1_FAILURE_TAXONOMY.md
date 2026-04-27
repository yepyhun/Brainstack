# P0/P1 Failure Taxonomy

This taxonomy drives GA release decisions. P0/P1 cannot be hidden as known limitations.

## P0

- Brainstack install shrinks native Hermes capability.
- Side-effect tool executes without approval.
- Secret, private path, raw log, or raw transcript leaks into model-facing packet or public artifact.
- Durable memory crosses user, scope, guild, or project boundary.
- Assistant hallucinated self/user/tool/runtime claim becomes durable truth or answer evidence.
- Source, wizard install, Docker image, or release artifact mismatch makes build unreproducible.
- Migration, upgrade, or cleanup loses data without backup/restore path.
- Product READY claimed from helper-only or manual-only proof.

## P1

- Preferred name, platform handle, identity slot, project metadata, or explicit reference URL recalls wrong.
- User correction fails to supersede or mark prior bad assistant claim corrected false.
- URL, file, web, or terminal task gets final content guess without tool result or unavailable diagnostic.
- Capability catalog lies about web/browser/file/terminal availability.
- Terminal/file capability false "no access" while manifest says configured available.
- Current assignment invented from Pulse/background/runtime noise.
- Support-only or inspect-only evidence becomes answer truth.
- Supported conversation path silently waits beyond SLO.
- Explicit style preference is ignored on the live final delivery path after correction.

## P2

- Non-core latency outlier with visible progress.
- Web/browser not configured, with honest unavailable diagnostic.
- Cheap model tone weakness when presentation hygiene and semantic correctness pass.
- Non-critical tool result truncation with continuation reference.

## P3

- Cosmetic doc issue.
- Non-blocking dashboard display issue.
- Optional provider matrix gap outside supported scope.

## Owner Requirement

Every P0/P1 failure must have:

- owner classification;
- repairability classification;
- failure bundle;
- minimal retest;
- blast-radius retest;
- READY/BLOCKED impact.
