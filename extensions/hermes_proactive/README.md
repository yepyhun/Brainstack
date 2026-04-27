# Hermes Proactive Extension

Optional Hermes runtime extension for proactive wake, PulseProducer, Evolver bridge, surfacing, and control UX.

Brainstack remains the memory kernel. This extension calls Brainstack public SDK/projection APIs and owns runtime behavior.

## Modes

```text
disabled
dry_run
live
```

Default install mode must be `disabled` or `dry_run`; never silently `live`.

## Dependencies

Current extension code uses stdlib plus the installed Brainstack SDK/projection API.

It does **not** install Evolver itself. The Evolver bridge consumes a health/status file when present. If full Evolver installation is needed later, it should be a separate explicit wizard option such as `--install-evolver`, not hidden behind proactive extension install.

## Boundary

- Hermes owns heartbeat, scheduling, delivery, approval, and execution.
- Extension owns producer/surfacing/control UX.
- Brainstack owns proactive memory projection and inspectable state.
- Extension must not write Brainstack private SQLite tables directly.
