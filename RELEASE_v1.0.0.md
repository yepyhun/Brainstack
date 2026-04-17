# Brainstack v1.0.0

Brainstack 1.0 marks the first stable release of the Hermes-native memory kernel and installer path.

## What 1.0 means

- One durable memory owner inside Hermes for continuity, profile facts, graph truth, and corpus retrieval
- Explicit shelf separation instead of a flat memory blob
- Durable identity and communication contract retrieval hardened for direct self-fact recall
- Practical logistics memory bounded so stable provider and place facts persist, while reminders stay owned by Chron
- Installer and doctor now target an existing Hermes checkout and selected agent config, without auto-creating an agent
- Docker install path is reproducible, including readiness healthchecks and runtime ownership normalization

## Included in this release

- Donor-composed memory kernel with Hindsight-aligned continuity, Graphiti-shaped graph truth, and MemPalace-shaped corpus retrieval
- Brainstack-only personal memory ownership gates for host runtime surfaces
- RTK sidecar integration for bounded tool-result handling
- Generic installer flow for existing Hermes checkouts
- Doctor checks for plugin wiring, runtime boundaries, Docker readiness, and agent-target correctness

## What this release does not do

- It does not create or choose an agent for the user
- It does not replace Chron as the reminder or scheduler owner
- It does not depend on a branded runtime layout

## Upgrade notes

- Select or create a Hermes agent config first
- Run the Brainstack installer against that explicit config
- In Docker mode, if no compose file exists for that agent, the installer can generate one

## Release target

- Tag: `v1.0.0`
- Commit: `5bfe590`
