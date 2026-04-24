# Phase 41 Audit Log

This file is append-only during the audit so detailed findings survive context compaction.

## Batch 1

### 1. Discord slash command sync failure

- surface:
  - deployed Hermes/Bestie gateway runtime
- proof:
  - live/runtime logs showed:
    - `In group 'skill'`
    - `Command exceeds maximum size (8000)`
- accepted reading:
  - the previous Discord `/skill` command representation exceeded Discord payload limits
  - this was a real live deploy issue, not a theoretical edge case
- current status:
  - fixed locally in deployed checkout by compact `/skill` representation
  - still needs classification in the full audit as:
    - historical live defect
    - source-vs-deploy parity question

### 2. Route-resolution and auxiliary payment failures

- surface:
  - deployed runtime logs
- proof:
  - OpenRouter `402` failures on:
    - Brainstack route resolution
    - auxiliary memory paths
- accepted reading:
  - this is a real runtime risk surface
  - the audit must determine:
    - whether fallback remains truthful
    - whether this violates fail-closed expectations
    - whether this is provider economics, source logic, or both

### 3. CA bundle path drift

- surface:
  - Hermes auth/runtime warning
- proof:
  - warning that configured CA bundle path did not exist and runtime fell back to default certificates
- accepted reading:
  - environment or deploy drift is present
  - not yet classified as source defect
  - still relevant for strict operational inspection

## Batch 2

### 4. Control-plane routing is still not fully owner-first

- surface:
  - `plugins/memory/brainstack/control_plane.py`
- proof:
  - residual query-shape analysis still exists:
    - `HIGH_STAKES_TERMS`
    - `_contains_any(...)`
    - `analyze_query(...)`
    - `profile_slot_targets`
    - `operating_like`
    - `task_like`
  - those flags still tune policy:
    - `if analysis.profile_slot_targets:`
    - `if analysis.operating_like:`
    - `if analysis.task_like:`
    - `if analysis.high_stakes:`
- accepted reading:
  - this is no longer the older broad cue-farm state
  - but it is still residual heuristic policy shaping
  - owner-first routing completion is not finished
- principle impact:
  - partial tension with:
    - `Zero heuristic sprawl`
    - `Truth-first / no "good enough"`

### 5. Executive route selection still depends on cue tables and route fallback

- surface:
  - `plugins/memory/brainstack/executive_retrieval.py`
- proof:
  - explicit cue families are still present:
    - `AGGREGATE_ROUTE_CUES`
    - `STYLE_CONTRACT_STRONG_CUES`
    - temporal cue families
  - route resolution still has multiple non-owner-first branches:
    - deterministic cue route
    - optional LLM route resolver
    - failure path:
      - `route.source = "route_resolution_failed"`
      - `route.reason = "route resolver failed; staying on fact route"`
    - unsupported payload/mode also collapse to failed fact route
  - unsupported routed modes later collapse back to fact:
    - `if route.applied_mode != ROUTE_FACT and not _route_has_support(route, selected):`
    - `route.fallback_used = True`
    - `route.applied_mode = ROUTE_FACT`
- accepted reading:
  - the fallback is now explicit and more truthful than before
  - but retrieval semantics still depend on route hints, cue detection, provider success, and support-availability checks
  - provider economics or auxiliary call failure can still change the final surfaced route
- principle impact:
  - residual tension with:
    - `Fail-closed upstream compatibility`
    - `Zero heuristic sprawl`

### 6. Retrieval still exposes multi-authority fallback semantics

- surface:
  - `plugins/memory/brainstack/retrieval.py`
- proof:
  - exact contract recall explicitly says:
    - `This is the canonical archival behavior contract ...`
    - `It is not the same thing as the smaller ordinary-turn invariant lane.`
  - task lookup semantics still expose:
    - `structured_miss_with_fallback`
    - `fallback_sources`
    - `Lookup path used supporting shelves only`
  - style-contract rows are still filtered differently by route:
    - `route_mode != "style_contract"`
    - `preserve_style_contract`
- accepted reading:
  - this is more truthful than silently pretending all surfaces are the same
  - but it is still a residual multi-authority system where exact recall, ordinary-turn guidance, and fallback shelves can diverge
  - the system is not yet at a single perfectly converged memory truth surface
- principle impact:
  - residual product debt against:
    - `Coherent continuous conversation`
    - `Long-range accurate recall and relation-tracking`

## Batch 3

### 7. Cross-community coupling is still very high

- surface:
  - architecture overview from code-review-graph on `/home/lauratom/Asztal/ai/hermes-final`
- proof:
  - `31 communities`
  - `6074 cross-community edges`
  - `19 warning(s)`
  - strongest warnings include:
    - high coupling between `gateway-no` and `tools-check`
    - high coupling between `platforms-send` and `gateway-no`
    - high coupling between `hermes-cli-provider` and `gateway-no`
    - high coupling between `agent-tool` and `gateway-no`
- accepted reading:
  - this is not proof of a single correctness bug
  - it is proof of substantial modularity debt and large blast radius
  - a strict inspector can reasonably call out architectural over-coupling
- principle impact:
  - tension with:
    - `Modularity / Upstream updateability`
    - `Donor-first`

### 8. Gateway/platform runtime is still bridge-node heavy

- surface:
  - bridge-node analysis from code-review-graph
- proof:
  - top bridge nodes include:
    - `GatewayRunner`
    - `PlatformConfig`
    - `DiscordAdapter`
    - `TelegramAdapter`
    - `FeishuAdapter`
  - those nodes connect multiple regions with high betweenness
- accepted reading:
  - platform runtime orchestration is still concentrated in a small set of chokepoints
  - local defects in these nodes can have wide downstream effects
  - this increases inspection risk even when tests are present
- principle impact:
  - tension with:
    - `Modularity / Upstream updateability`
    - long-term maintainability expectations

### 9. There are still giant untested or weakly test-targeted hotspot functions

- surface:
  - large-function and knowledge-gap analysis from code-review-graph
- proof:
  - very large functions include:
    - `AIAgent.run_conversation` — `3139` lines
    - `hermes_cli.main.main` — `1688` lines
    - `HermesCLI.run` — `1623` lines
    - `GatewayRunner._run_agent` — `1458` lines
    - `run_doctor` — `968` lines
  - graph-reported untested hotspots include:
    - `run_conversation`
    - `run_doctor`
    - `ChatConsole.print`
    - `gateway_command`
- accepted reading:
  - this is direct spaghetti / maintainability debt
  - even where surrounding flows have tests, these hubs remain high-risk for hidden regressions and difficult inspection
- principle impact:
  - tension with:
    - `Truth-first / no "good enough"`
    - long-term operational robustness

## Batch 4

### 10. Gateway stream delivery still contains explicit best-effort fallback seams

- surface:
  - `gateway/stream_consumer.py`
- proof:
  - mid-stream edit failures trigger fallback mode:
    - `if self._fallback_final_send or not ok:`
    - `fallback final-send path`
  - final delivery can switch to a single continuation/fallback send
  - cursor-stripping helper swallows exceptions:
    - `except Exception:`
    - `pass  # best-effort — don't let this block the fallback path`
  - edit-not-supported paths also drop to fallback final-send behavior
- accepted reading:
  - this is pragmatic delivery hardening, not an obvious correctness bug
  - but it is still explicit degrade-open / best-effort behavior in a user-visible path
  - a strict inspector can legitimately classify this as operational fallback debt
- principle impact:
  - partial tension with:
    - `Fail-closed upstream compatibility`

### 11. Gateway boot/runtime still carries deprecated compatibility and fallback model seams

- surface:
  - `gateway/run.py`
- proof:
  - deprecated env fallback remains:
    - `MESSAGING_CWD is accepted as a backward-compat fallback`
  - model fallback chain remains active:
    - `_load_fallback_model()`
    - reads both:
      - `fallback_providers`
      - legacy `fallback_model`
  - restart behavior intentionally exits with code `1` so:
    - `systemd Restart=on-failure can revive the gateway`
- accepted reading:
  - this is not hidden anymore; the code comments are explicit
  - but it is still a compatibility-heavy boot/runtime surface with layered fallbacks and operator-dependent semantics
  - inspector risk is high because this mixes configuration bridging, backward compatibility, and recovery behavior in the same boot path
- principle impact:
  - tension with:
    - `Modularity / Upstream updateability`
    - `Truth-first / no "good enough"`

## Batch 7

### 18. Live Bestie style authority can remain polluted after code-side fixes

- surface:
  - live Bestie store
  - `plugins/memory/brainstack/__init__.py`
  - `plugins/memory/brainstack/db.py`
- proof:
  - the live `behavior_contracts` active row can still carry introspection-heavy polluted content instead of one clean style authority revision
  - the same live store can have no compiled `behavior_policies` row at all
- accepted reading:
  - code-side repair paths exist
  - but the live runtime does not yet guarantee convergent authority state on startup or first read
  - a strict inspector can legitimately say the product is not self-healing enough in deployed chat
- principle impact:
  - tension with:
    - `Truth-first / no "good enough"`
    - `Fail-closed upstream compatibility`

### 19. Final-output enforcement can go inactive when live compiled policy is absent

- surface:
  - `plugins/memory/brainstack/output_contract.py`
  - `plugins/memory/brainstack/__init__.py`
  - host final-output path
- proof:
  - without compiled policy, output validation drops into an inactive state
  - live chat can then emit emoji and other contract violations even while style authority text still exists
- accepted reading:
  - this is not only a memory-recall problem
  - it is a product-level obedience failure where known rules are not guaranteed to govern shipped output
- principle impact:
  - tension with:
    - `Truth-first / no "good enough"`
    - `Fail-closed upstream compatibility`

### 20. Natural style-recall questions still miss owner-first routing

- surface:
  - `plugins/memory/brainstack/profile_contract.py`
  - `plugins/memory/brainstack/control_plane.py`
  - `plugins/memory/brainstack/retrieval.py`
- proof:
  - natural questions such as `miért nem tartod be a szabályokat` can still drift into transcript or session recall instead of style authority lookup
  - the current direct style-route patterns remain narrower than the ordinary live phrasing users actually use
- accepted reading:
  - residual owner-first routing debt still exists exactly on a high-value live path
  - this is not permission to add a cue farm; it is a sign that the authority signal is still too weakly exposed
- principle impact:
  - tension with:
    - `Zero heuristic sprawl`
    - `Truth-first / no "good enough"`

### 21. Gateway transcript persistence has a live field-mismatch bug

- surface:
  - `gateway/session.py`
- proof:
  - live logs show transcript persistence failing with:
    - `'SessionEntry' object has no attribute 'model'`
  - the persistence path reads `entry.model` even though the recorded session entry shape does not supply that field
- accepted reading:
  - continuity and transcript-backed recall cannot be considered trustworthy while this write path is broken
  - this is host correctness debt, not just memory-kernel nuance
- principle impact:
  - tension with:
    - `Truth-first / no "good enough"`
    - `Coherent continuous conversation`

### 22. Internal tool traces still leak into the user-facing chat surface

- surface:
  - host runtime streaming / display path
  - `run_agent.py`
- proof:
  - live chat showed user-visible lines such as:
    - `cronjob: "list"`
    - `session_search: ...`
    - `Interrupting current task ...`
- accepted reading:
  - operator/debug traces are still crossing into the product surface
  - this harms chat coherence, professionalism, and token discipline
- principle impact:
  - tension with:
    - `Coherent continuous conversation`
    - `Meaningful token savings`

### 23. Reminder scheduling correctness is still not trustworthy enough

- surface:
  - host scheduling / cron integration path
- proof:
  - the reminder incident showed the live job was scheduled in UTC rather than intended local time semantics
  - the user experienced the miss as a product failure, not as an isolated cron implementation detail
- accepted reading:
  - scheduling correctness is part of the live second-brain promise
  - the current behavior is too brittle for inspector-grade confidence
- principle impact:
  - tension with:
    - `Truth-first / no "good enough"`
    - `Proactive stateful continuity`

### 12. Session and memory subsystems still carry legacy dual-storage compatibility debt

- surface:
  - `gateway/session.py`
  - `plugins/memory/hindsight/__init__.py`
- proof:
  - session storage still supports dual-mode transcript persistence:
    - SQLite
    - legacy JSONL
  - file comments explicitly state:
    - `Falls back to legacy JSONL files if SQLite is unavailable`
    - `using JSONL (legacy session not yet fully migrated)`
  - hindsight config still loads from:
    - profile-scoped path
    - legacy shared `~/.hindsight/config.json`

## Batch 6

### 17. Final-output typed invariant enforcement is incomplete

- surface:
  - `plugins/memory/brainstack/output_contract.py`
  - `plugins/memory/brainstack/__init__.py`
  - `agent/brainstack_mode.py`
  - `run_agent.py`
- proof:
  - `forbid_all_dash_like` is compiled as a typed punctuation constraint
  - `validate_output_against_contract(...)` records `remaining_violations` for `dash_like_punctuation`
  - that same validator returns `repair = "none"` for the strong dash-like prohibition branch
  - the provider trace records `remaining_violation_count`
  - the final response path only returns `result["content"]`
  - the runtime does not fail-closed, retry, or block on remaining typed invariant violations
- accepted reading:
  - this is not just a dash-specific symptom
  - this is a broader kernel bug class:
    - typed invariant detected
    - violation known
    - answer still shipped
  - the current final-output enforcement layer is still partially advisory for at least one live user-facing invariant family
- principle impact:
  - direct tension with:
    - `Fail-closed upstream compatibility`
    - `Truth-first / no "good enough"`
  - indirect tension with:
    - `Coherent continuous conversation`
    - `Meaningful token savings`
      because prompt-side authority is being spent on invariants that are not yet reliably enforced
    - env vars
  - hindsight also preserves legacy alias behavior:
    - `"local" is a legacy alias for "local_embedded"`
- accepted reading:
  - this is not necessarily wrong during transition
  - but it is a real operational and conceptual debt surface
  - dual-storage / dual-config compatibility increases ambiguity, migration burden, and inspection attack surface
- principle impact:
  - tension with:
    - `Modularity / Upstream updateability`
    - operational clarity expectations

### 13. Legacy graph extractor still exists as compatibility debt even after live ingest was hardened

- surface:
  - `plugins/memory/brainstack/legacy_graph_text_extractor.py`
  - `plugins/memory/brainstack/graph_evidence.py`
- proof:
  - the typed boundary file is now clean and explicit:
    - `GraphEvidenceItem`
    - `GraphEvidenceIngressError`
    - typed boundary versioning
  - but the legacy extractor still exists with text-pattern behavior:
    - `STATUS_WORDS`
    - `SUPERSEDE_MARKERS`
    - `extract_graph_evidence_from_text(...)`
- accepted reading:
  - the live default path is better than before
  - but the legacy heuristic extractor still exists in-repo and remains part of compatibility burden and future drift risk
  - this is now debt rather than current primary live behavior
- principle impact:
  - tension with:
    - `Zero heuristic sprawl`
    - long-term cleanup expectations

## Batch 5

### 14. The proof surface is broad, but major hubs still have direct-coverage debt

- surface:
  - code-review-graph knowledge-gap analysis
  - targeted test lookup across `tests/`
- proof:
  - graph reports:
    - `38 test gaps` in minimal context
    - `87 total gaps` in knowledge-gap summary
    - `20 untested hotspots`
    - `50 isolated nodes`
  - flagged untested hotspots include:
    - `AIAgent.run_conversation`
    - `run_doctor`
    - `ChatConsole.print`
    - `gateway_command`
    - `GatewayRunner._handle_message_with_agent`
  - direct test lookup shows many references to these hubs are indirect or mock-based rather than direct high-fidelity execution coverage
- accepted reading:
  - the repo does have a large test suite
  - but inspector-grade confidence is still weaker on the biggest orchestration hubs than raw test-count alone suggests
  - this is proof debt, not just coverage-count debt
- principle impact:
  - tension with:
    - `Truth-first / no "good enough"`

### 15. Single-file and isolated-node patterns suggest hidden maintainability islands

- surface:
  - code-review-graph knowledge-gap analysis
- proof:
  - `15 single-file communities`
  - `2 thin communities`
  - `50 isolated nodes`
  - examples include standalone communities around:
    - `cli.py`
    - `mcp_serve.py`
    - `trajectory_compressor.py`
    - `toolsets.py`
  - isolated interface-like methods still appear in:
    - `agent/context_engine.py`
    - `agent/memory_provider.py`
    - several agent/runtime support modules
- accepted reading:
  - not every isolated node is a bug
  - but this pattern suggests fragmented architecture zones, local abstractions with weak graph connectivity, and possible dead-angle maintenance cost
  - a strict inspector can reasonably ask why these islands exist and whether they are deliberate seams or accidental fragmentation
- principle impact:
  - tension with:
    - `Modularity / Upstream updateability`

### 16. Large orchestration functions remain a systemic inspection liability even where tests exist

- surface:
  - large-function analysis
  - affected-flow analysis
- proof:
  - very large orchestrators remain central to live flows:
    - `AIAgent.run_conversation` — `3139` lines
    - `GatewayRunner._run_agent` — `1458` lines
    - `GatewayRunner._handle_message_with_agent` — `803` lines
    - `GatewayRunner._handle_message` — `594` lines
    - `GatewayRunner.run_sync` — `560` lines
    - `gateway/config.py::_apply_env_overrides` — `410` lines
  - affected-flow analysis shows current changes still propagate through:
    - `GatewayRunner`
    - `SessionStore`
    - session-agent runtime resolution
    - stream-consumer delivery
- accepted reading:
  - this is more than stylistic discomfort
  - it means change blast radius, debugging cost, and correctness review burden remain structurally high
  - a strict inspector can legitimately call this spaghetti-risk even if the code still works
- principle impact:
  - tension with:
    - `Modularity / Upstream updateability`
    - `Truth-first / no "good enough"`
