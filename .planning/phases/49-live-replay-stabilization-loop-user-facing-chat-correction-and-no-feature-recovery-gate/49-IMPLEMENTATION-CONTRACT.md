# Phase 49 Implementation Contract

## invariant

The live Bestie chat path may not expose internal Brainstack enforcement, internal tool progress, or unresolved authority drift to the user. Real failing chats must be recoverable through one bounded replay-and-correction loop without adding new product capability.

## canonical principle reference

Use the canonical principles file directly:
- `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`

Pinned names that must govern this phase:
- `Donor-first`
- `Modularity / Upstream updateability`
- `Fail-closed upstream compatibility`
- `No benchmaxing`
- `Truth-first / no "good enough"`
- `Zero heuristic sprawl`
- `Multimodal-first architecture`
- `The donor-first elv marad`

## required properties

- replay pack is built from real failing chats, not synthetic benchmark prompts
- blocked Brainstack validation never becomes user-facing internal blocker text
- internal tool progress never becomes ordinary user-facing chat output
- natural rule-recall questions route to style authority on the live path
- active style authority and compiled policy stay converged on the live path
- transcript persistence is correct on the host path
- reminder scheduling and display are correct for the live user-facing path
- every correction batch reruns the full replay pack
- the final proof artifact shows all acceptance metrics green on the docker/live path

## prohibited outcomes

- adding new memory capability or new retrieval feature work during this phase
- broad heuristic or language-specific cue farms as the main recovery mechanism
- shipping a user-visible blocker message as “acceptable fail-closed behavior”
- declaring phase success from local slice tests while the full replay pack still fails
- masking regressions with prompt-only band-aids instead of correcting the runtime path

## required verification artifact

Produce one bounded replay proof artifact that records:
- replay case list
- per-case pass/fail
- `blocked_user_leak_count`
- `tool_trace_leak_count`
- `style_recall_success`
- `authority_ready_when_active`
- `final_output_compliance`
- `transcript_persist_errors`
- `reminder_timezone_correct`
- docker/live replay result

## recommended model level

`xhigh`
