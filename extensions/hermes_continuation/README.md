# Hermes Continuation Extension

Optional runtime addon for Hermes continuation decisions.

Brainstack remains the memory kernel. This extension is a separate, inert
decision layer that can be installed next to Hermes and used by a runtime
adapter or orchestration layer.

It does not execute work, send messages, mutate Kanban, run Evolver, or approve
external side effects. It only turns compact runtime evidence into public-safe
verdicts and next-action decisions.

Core loop:

```text
observe -> score -> forecast -> act -> check -> learn -> repeat
```

Allowed decisions:

- `continue`
- `split`
- `verify`
- `repair`
- `learn`
- `wait`
- `human_needed`

Additional contracts:

- capability assignment: reject unknown or incapable workers before work is
  considered runnable.
- completion proof: a worker cannot claim "done" without artifact, evidence,
  verdict, postcondition, and sufficient proof strength.
- Work Graph: describe fan-out, fan-in, repair, and terminal states without
  mutating Kanban.
- decision trace replay: rebuild compact recovery state after restart and
  suppress duplicate events.

The extension is safe to ship publicly because domain-specific adapters,
private project policies, and private artifacts are not included here.
