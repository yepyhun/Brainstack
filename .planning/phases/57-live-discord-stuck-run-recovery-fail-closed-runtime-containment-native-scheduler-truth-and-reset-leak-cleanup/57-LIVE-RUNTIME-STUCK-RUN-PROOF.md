# Phase 57 Live Runtime / Fail-Closed Proof

## Source-of-truth graph fail-closed proof

Installed target proof used the patched `finafina` checkout after source-of-truth install.

### provider-init failure containment

Monkeypatch proof on installed runtime:

- graph backend open raised `std::bad_alloc`
- `BrainstackStore.open()` did not abort
- resulting state:
  - `_graph_backend is None`
  - `_graph_backend_error == "std::bad_alloc"`
  - `graph_backend_channel_status()["status"] == "degraded"`

This proves provider init no longer stays misleadingly half-alive on graph open failure.

### runtime graph failure containment

Monkeypatch proof on installed runtime:

- graph search failure `KuzuGraphBackend is not open`
- `search_graph(...)` fell back to SQLite
- backend was disabled after the first failure
- repeated active-path reuse of the dead backend no longer happened in the same store instance

### publish failure containment

Monkeypatch proof on installed runtime:

- `publish_entity_subgraph(...)` failure recorded a failed journal row
- backend was disabled
- the failure did not re-raise into the active caller path

## Installed-runtime log proof

Before Phase 57, the live logs showed:

- `Memory provider 'brainstack' initialize failed: std::bad_alloc`
- repeated `Brainstack graph search failed; falling back to SQLite: KuzuGraphBackend is not open`

After the Phase 57 install + rebuild:

- post-restart log window no longer showed fresh `std::bad_alloc`
- post-restart log window no longer showed fresh `KuzuGraphBackend is not open`

## Bounded runtime containment

Installed target config after Phase 57:

- `agent.gateway_timeout = 120`
- `agent.gateway_timeout_warning = 30`

This replaces the stale `1800/900` inactivity defaults on targets that still carry the upstream default values.

## Residual note

This proof covers source-of-truth install, fail-closed behavior, and bounded containment.

It does not replace the final real Discord UI proof.
