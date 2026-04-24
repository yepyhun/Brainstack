# State

## Status
planning_complete

## Guiding Principles

Canonical immutable source:
- [IMMUTABLE-PRINCIPLES.md](./IMMUTABLE-PRINCIPLES.md)

Pinned rule:
- do not paraphrase, soften, expand, or reinterpret the top-level project principles in other GSD artifacts unless the user explicitly changes them
- `STATE.md` may describe current strategy and current focus, but the governing principles live only in the canonical immutable file above

### Current Strategic Reading

- the project must be judged against the product targets above, not only against bounded oracle wins
- live deployment evidence outranks benchmark-shaped momentum when choosing the next phase
- broader capability work is only correct when it preserves donor-first updateability and improves real conversation quality rather than just benchmark coverage

## Current Focus
Immutable principles remain pinned here:
- [IMMUTABLE-PRINCIPLES.md](./IMMUTABLE-PRINCIPLES.md)

Latest planning truth:

- a new Brainstack-only phase `63.1` was inserted before the runtime-heavy `64`
- the explicit architectural anti-rule is now frozen:
  - the memory kernel may store and project durable policy/state truth
  - it may not become scheduler, executor, approval governor, or hidden runtime brain
- the immediate planning target is no longer "go straight to runtime intake"
- that Brainstack-only target was completed in `63.1`
- the runtime follow-up is no longer blocked on `63.1`

Latest execute truth:

- `63.1 execute` is complete
- Brainstack now has a canonical durable policy authority surface that is separate from:
  - transcript/continuity evidence
  - procedural skills
  - native compatibility memory
- the practical authority model is now:
  - `canonical policy`
  - `operating/live state`
  - `evidence`
- support stores remain:
  - `skill` for procedure
  - native memory for compatibility/support
- canonical policy promotion is explicit-only
- the memory kernel non-governor rule is now reflected in:
  - immutable principles
  - roadmap ordering
  - Brainstack public surface
- runtime `64` remains a separate next step and may only consume this new policy surface read-only
- `64 execute` is now complete as a bounded runtime consumer slice:
  - explicit inbox JSON envelopes are consumed at session start
  - runtime mirrors typed handoff tasks into Brainstack through Brainstack-owned APIs
  - first-turn runtime context now consumes canonical policy, approval policy, live state, and pending handoff tasks read-only
  - no transcript scraping or free-text domain/risk routing was introduced
  - no runtime governor loop was claimed
- paired live runtime bugfixes are also complete:
  - Tier-2 default caller no longer sends the invalid request shape that produced live `400 Invalid input`
  - startup compression is bounded and pinned to the main Kimi route to reduce pre-response stall pressure
  - `web_tools` metadata no longer causes credential-pool lookup during builtin tool discovery
- current verified proof after the final rebuild:
  - targeted proof suite: `118 passed`
  - broader regression ring: `322 passed`
  - live container healthy after rebuild
  - post-rebuild log scan contains no new `Invalid input`, `BadRequestError`, or `Agent idle for 120s` cached-turn stall lines

- strategic reset:
  - the current recovery direction changes from incremental host-side stabilization to donor-first de-escalation
  - the fresh upstream Hermes baseline is now `/home/lauratom/Asztal/ai/finafina` on `main` at `2cdae233e2a869656b194baa9be0bc6eef6d988f`
  - `50` supersedes `49` wherever they conflict on execution strategy
  - the target product is a thin orchestration shell around donor memory layers, not a host-level rule-governance system
  - fresh live proof must run against a clean runtime/profile baseline, not historically drifted Bestie state

- immediate planning target:
  - write and execute a donor-first de-escalation recovery plan against the fresh upstream checkout
  - identify the minimum viable extension seams:
    - `agent/memory_provider.py`
    - `agent/memory_manager.py`
    - `plugins/memory/*`
    - `run_agent.py`
    - `gateway/run.py`
    - `gateway/session.py`
    - `tools/cronjob_tools.py`
  - remove or sharply reduce host-level hard behavior gating before adding any new recovery logic
  - end the phase with a rolling live-test-and-rethink loop only after the simplification work is mostly complete

- next architecture decision to lock:
  - Phase `52` must re-anchor explicit user/profile truth to Hermes native `USER.md` / `MEMORY.md`
  - Brainstack should remain a donor-first memory kernel that mirrors and augments native memory writes, not a parallel first-class profile governor
  - the key output is a file-level keep / demote / remove / re-anchor map so later execution does not regress into host-side rule governance again

- `36 execute` is complete in the source Brainstack repo
- the landed packet-collapse changes target combined hot-path quality rather than adding new owners or new routing farms:
  - `brainstack/retrieval.py`
  - `brainstack/control_plane.py`
  - `brainstack/__init__.py`
  - `scripts/install_into_hermes.py`
  - `tests/test_brainstack_phase36_packet_quality.py`
  - `tests/test_install_into_hermes.py`
- the implementation now uses a shared system-substrate projection so ordinary-turn packet assembly can see what the substrate already rendered
- duplicate bounded contract rendering is suppressed when the same ordinary-turn lane is already present in the system substrate
- repeated stable profile keys already rendered by the substrate are suppressed from the working-memory block
- `Evidence Priority` is suppressed from the working-memory block when the substrate already carries `Truthful Memory Operations`
- the substrate no longer duplicates stable profile entries already rendered inside `Operating Context`
- recent continuity rows are suppressed when matched continuity already covers the same turn/evidence
- transcript rows now suppress against continuity overlap with a bounded fallback instead of silently erasing the channel
- the installer patch now softens the host memory-wrapper note so it behaves as a support/boundary layer rather than a second strong authority upgrade
- source proof after the execute cut:
  - changed-surface `ruff` checks: green
  - targeted phase `36 + retrieval + transcript + phase34 + phase35 + installer` gate: `34 passed, 1 warning`
  - broader guard across `30.2 + 30.3 + 35 + older packet/proof seams`: `52 passed, 1 warning`
- named non-blocker:
  - `tests/test_brainstack_real_world_flows.py` still fails collection on the older `plugins.memory.brainstack` import seam
  - this pre-existing harness drift was not treated as a Phase 36 product regression
- `36 verify` is now complete
- verify truth:
  - the first `hermes-final` refresh attempt exposed two installer drift seams rather than a Phase 36 product regression:
    - `memory_manager.py` still used the older authoritative private-recall note variant
    - the target Dockerfile had moved to a newer cache-layered backend dependency layout
  - both installer seams were hardened in the source installer and the installer regression suite remained green: `17 passed`
  - the refreshed `hermes-final` install succeeded and the doctor stayed green
  - payload parity is exact for:
    - `retrieval.py`
    - `control_plane.py`
    - `__init__.py`
    - `brainstack_doctor.py`
  - the refreshed `hermes-final` host seam is updated:
    - `agent/memory_manager.py` now contains the softer `supporting memory context` wording
    - the older `authoritative over assistant suggestions` phrase is absent
  - direct `hermes-final` interpreter proof is green:
    - combined packet chars: `1858`
    - contract section count: `1`
    - identity count: `1`
    - `Evidence Priority` absent from the working-memory block when substrate semantics are already present
    - wrapped memory-context note count: `1`
    - continuity collapse preserves the deployment-window / rollback-owner facts while suppressing `Recent Continuity`
  - rebuilt live runtime proof is green:
    - `./scripts/hermes-brainstack-start.sh rebuild` completed successfully
    - image `hermes-bestie-hermes-bestie:latest` rebuilt to `03a69e1f30a0`
    - recreated `hermes-bestie` is `healthy`
    - container hashes for `retrieval.py`, `control_plane.py`, and `__init__.py` match the refreshed payload
    - container `memory_manager.py` matches the softened host seam wording
    - live runtime packet metrics match the direct proof:
      - combined chars `1858`
      - contract section count `1`
      - identity count `1`
      - working-memory `Evidence Priority` section absent
      - wrapped memory-context note count `1`
    - live continuity-collapse smoke also matches the direct proof

- `35 execute` is complete in the source Brainstack repo
- the landed operating-substrate changes are:
  - first-class `operating_records` storage now exists for:
    - `active_work`
    - `open_decision`
    - `current_commitment`
    - `next_step`
    - `external_owner_pointer`
  - explicit operating truth now commits through a dedicated `brainstack.operating_truth` owner path
  - operating context now prefers committed operating truth over continuity-derived fallback summaries
  - retrieval now consults operating truth as its own owner-backed shelf instead of relying only on query-shape cue pruning
  - the phase did not widen behavior governance or add a new heuristic marker farm
- source proof after the execute cut:
  - targeted phase `35 + 34 + 33 + 30.5 + retrieval` gate: `17 passed, 1 warning`
  - connected `operating_context + executive_retrieval + graph_evidence` guard suite: `21 passed, 1 warning`
  - installer regression suite: `17 passed`
  - changed-surface `ruff` checks: green
- `35 verify` is now complete
- verify truth:
  - installer refresh into `hermes-final` succeeded and doctor parity stayed green after adding the new `operating_truth.py` seam
  - payload parity is exact for the installed plugin surface: `37 / 37` files with no hash mismatch
  - direct `hermes-final` interpreter proof is green:
    - operating truth commits through the dedicated owner path
    - operating context renders committed operating truth
    - operating query recall surfaces the committed `next_step`
  - rebuilt live runtime proof is green:
    - the first live verify attempt exposed a stale runtime image, not a product regression
    - a clean rebuild produced image `sha256:88a8ceb3ecd51797113f6539852163556c858d9160c21cbdaef3231136b246d6`
    - recreated `hermes-bestie` now runs that exact image and is `healthy`
    - container hashes match the refreshed payload for:
      - `db.py`
      - `operating_truth.py`
      - `operating_context.py`
      - `control_plane.py`
      - `executive_retrieval.py`
      - `retrieval.py`
      - `__init__.py`
    - live container smoke proves:
      - committed operating-truth receipt is present with owner `brainstack.operating_truth`
      - `operating_records` table exists in the live plugin DB
      - all five bounded operating record types persist
      - operating query recall renders `## Brainstack Operating Truth`
      - committed `next_step` survives live retrieval

- `34 execute` is complete in the source Brainstack repo
- the landed role-split / de-harness changes are:
  - ordinary-turn behavior injection is now an explicitly smaller pinned invariant lane instead of a broad style-governance payload
  - exact canonical behavior-contract recall remains a separate lane with different authority and different rendering
  - memory-context authority wording no longer upgrades recalled behavior material to the same strength as factual user truth or committed owner-backed records
  - personal / preference routing now keeps more real transcript / graph / corpus evidence without forcing broad behavior governance into the hot path
  - no new heuristic marker farm or transcript-specific special casing was introduced to get the phase green
- source proof after the execute cut:
  - targeted phase `34 + 33 + retrieval + install` gate: `62 passed, 1 warning`
  - wider guard suite across `29 + 30.2 + 30.3 + 30 operating context`: `37 passed, 1 warning`
  - combined source proof across the touched phase surfaces: `99 passed, 1 warning`
- `34 verify` is now complete
- verify truth:
  - the source installer refreshed `hermes-final` successfully and the doctor stayed green on the relevant host/runtime seams
  - changed plugin payload parity is exact for:
    - `__init__.py`
    - `behavior_policy.py`
    - `retrieval.py`
    - `control_plane.py`
    - `executive_retrieval.py`
  - the `hermes-final` host seam is updated:
    - `agent/memory_manager.py` now uses the softer factual-authority wording
    - the old `name, number, date, or preference` authority phrase is absent
  - direct `hermes-final` interpreter smoke proves:
    - ordinary-turn prompt keeps the active contract lane
    - that lane is a bounded ordinary-turn invariant subset
    - expressive tone and every-reply follow-up-question rules are excluded from the ordinary-turn lane
    - explicit style-contract recall still returns the full canonical contract lane including those omitted rules
  - rebuilt live runtime proof is green:
    - `hermes-bestie` rebuilt from the refreshed checkout and is `healthy`
    - container hashes for `retrieval.py`, `behavior_policy.py`, and `control_plane.py` match the source payload
    - container `memory_manager.py` matches the refreshed host seam wording
    - the live smoke matches the direct interpreter proof for the same role-split invariants

- `33 execute` is complete in the source Brainstack repo
- the landed second-brain quality changes are:
  - personal truth lookup now has a bounded personal-scope fallback across workspace / adjacent runtime drift instead of relying only on exact principal scope
  - short explicit user corrections can now become durable canonical behavior-contract patches without requiring a full structured rule-pack resend
  - one-line invalid or corrective inputs no longer get accidentally merged with prior multi-line fragments into silent canonical contract rewrites
  - personal / preference turns can now keep the authoritative style contract visible when needed, instead of relying only on the compiled ordinary-turn projection
  - personal / preference routing no longer starves transcript / graph / corpus evidence as aggressively, reducing fake “I forgot” outcomes
- source proof after the execute cut:
  - targeted phase `33 + 30.5 + 30.2 + 29` gate: `37 passed, 1 warning`
  - retrieval / operating-context guard suites: `6 passed, 1 warning`
- `33 verify` is now complete
- verify truth:
  - `hermes-final` payload parity is exact:
    - source plugin files: `36`
    - installed plugin files: `36`
    - hash mismatches: `[]`
  - direct `hermes-final` interpreter smoke proves:
    - personal behavior-contract fallback survives workspace drift
    - short explicit user correction creates a canonical patch revision with `patch_rule_count = 1`
    - personal / preference turns keep the authoritative contract visible while preserving nonzero transcript / graph / corpus budgets
  - rebuilt live runtime proof is green:
    - the first live smoke failure was traced to a stale container image, not accepted as product truth
    - rebuild restored parity for all six changed Brainstack files between `hermes-final` and `/opt/hermes`
    - rebuilt `hermes-bestie` is `running` and `healthy`
    - the live smoke now matches the direct interpreter proof for the three phase invariants
- `34` is now planned as the next strategic kernel-shape phase after `33`
- `34` does not assume the user is absolutely right; it freezes a truth-first re-evaluation of Brainstack’s role:
  - keep Brainstack strong as a second-brain / continuity kernel
  - reduce the parts that behave like broad ordinary-turn prompt governance
  - split archival behavior recall from a smaller pinned invariant lane
  - restore stronger chat-first local reasoning synergy with the LLM
- `35` is now planned as the likely follow-on after `34`
- `35` captures the next zoomed-out product need:
  - Brainstack should become stronger at operating/world truth, not only behavior/answer truth
  - the operating context needs a small first-class operating-truth layer
  - retrieval should move closer to owner-first logic
  - the current truth classes should mature into a more coherent operating substrate without broad ontology sprawl

- `32 execute` is complete in the source Brainstack repo
- the bad mid-phase `session_search` marker-list blocker was explicitly rejected and removed as heuristic sprawl
- the actual landed fixes are:
  - structural inline `rule - explanation` style-contract parsing
  - multi-message operating-rule convergence across adjacent user fragments
  - direct first-class `behavior_contract` commit on explicit style-contract writes
  - stronger protection against lower-quality `tier2_llm` behavior-contract supersession
  - sequential-path installer patching against the real `handle_function_call(...)` seams
- source proof after the corrected execute cut:
  - targeted execute gate: `22 passed, 1 warning`
  - targeted host-boundary invariants: `2 passed`
- `32 verify` is now complete
- verify truth:
  - source / shim-proxy surface:
    - host-import-shim-backed tests remained green from the execute cut
  - `hermes-final` surface:
    - installed payload parity is exact: `35` source files vs `35` final files
    - direct interpreter smoke proves multi-message rule teaching now converges into one canonical first-class `behavior_contract`
  - rebuilt live runtime surface:
    - `hermes-bestie` is healthy on the rebuilt image
    - container hashes for `__init__.py`, `style_contract.py`, and `db.py` now match the final payload
    - direct container smoke proves:
      - first fragment alone does not commit
      - second fragment commits the canonical contract
      - receipt owner = `brainstack.behavior_contract`
      - `rule_count = 4`
      - `fragment_count = 2`
    - host seam proof in the container:
      - `guard_count = 3`
      - sequential blocking present
      - rejected `SESSION_SEARCH_*` marker-list blocker absent
- `30.5 execute` is now complete in the source Brainstack repo
- the canonical operating-rule truth no longer writes as a profile-lane raw owner:
  - dedicated `behavior_contracts` storage now holds the committed canonical contract
  - compiled behavior policy rebuilds from that first-class contract storage
  - explicit correction now creates canonical revisions instead of mutating an in-place profile row
  - explicit full-contract recall now fails closed when no committed canonical contract exists
- source-only validation after the execute cut:
  - targeted `30.5 + 29 + 30.2` regression gate: `31 passed, 1 warning`
  - additional retrieval / operating-context guard suites: `6 passed, 1 warning`
- remaining work for this phase is verify only:
  - shim parity
  - `hermes-final`
  - live runtime proof

Phase `29.1` through `29.4` remain valuable and mostly closed as bounded correctness work.

Phase `29.5` is **not** fully closed.

The newest live evidence says:

- the detailed canonical `preference:style_contract` row can exist in the DB with the full taught contract
- the remaining failures are no longer well-described as simple “storage loss”
- the live `27`-rule problem now spans:
  - route/runtime parity
  - ordinary-turn exclusion by design
  - delayed policy-teaching activation
  - and the larger absence of an always-on compiled behavior policy

The most useful accepted strategic reading from the external audit is:

- Brainstack is already reasonably strong as a bounded memory kernel
- but explicit user behavior rules are still not first-class enough as always-on runtime policy
- the repo currently separates:
  - compact operational contract
  - detailed archival contract
  incompletely for the user's actual use case
- the next real uplift is therefore not more retrieval micro-tuning
- it is a move toward:
  - raw archival behavior contract
  - compiled always-on behavior policy
  - synchronous teaching + activation
  - end-to-end obedience verification
  - observability / correction / runtime-parity closure
- the key contract going forward is explicit:
  - exact rule recall may use a dedicated archival recall lane
  - everyday rule obedience must not depend on the user phrasing the turn as a recall request
  - once compiled policy is active, it becomes the only ordinary-turn runtime authority for reply behavior
  - compiler behavior must be no-silent-drop: every taught rule receives a named outcome

Current strategic sequence:

- `29.5`
  - finish the immediate live exact-recall closure work with the newest route/runtime truth
- `29.6`
  - create the raw archival contract vs compiled always-on behavior policy split
- `29.7`
  - make explicit rule teaching synchronous and immediately active
- `29.8`
  - expand the behavior ontology without blowing up token costs
- `29.9`
  - add product-facing obedience and regression gates
- `29.10`
  - add behavior-policy observability, correction, doctor, and runtime-parity gates
- `30.0`
  - widen the same architecture into a true always-on second-brain / proactive-agent operating model
- `30.1`
  - separate long-form document / KG ambition from chat-time memory so the product does not confuse these problem classes
- `30.5`
  - close the now-proven multi-message operating-rule durability gap:
    - teaching a long rule pack across several user turns must still converge into one canonical raw contract
    - user rule corrections must become durable canonical revisions when the user intent is clearly persistent rule change
    - a reset must not erase a just-confirmed operating-rule change because the system only held it in session-local reinforcement or assistant paraphrase

New verify-surface rule learned during `29.6`:

- source-only proof is not enough for Brainstack behavior-policy work
- every future behavior-policy phase must explicitly verify all three surfaces:
  - source-of-truth Brainstack repo
  - shimmed Hermes worktree package used by `plugins.memory.brainstack` tests
  - `hermes-final` checkout/runtime surface
- a phase is not considered cleanly verified if one of those surfaces is stale while another is green

Protected reading for this next sequence:

- do not solve the behavior-policy problem with prompt-policing or output regexes
- do not create a second shadow memory owner beside Brainstack
- do not regress donor-first seams with local glue sprawl
- do not reintroduce broad handwritten Tier-1 semantic/profile inference
- do not spend the next cut on a broad KG redesign before the behavior-policy plane is fixed
- do not trade away multimodal readiness or token discipline for a quick obedience hack
- do not leave dual-write / dual-read / dead-code leftovers behind while the policy architecture evolves

Phase `28` and `28.1` remain open, but they stay paused until one direct user-facing UAT pass confirms the repaired reset path from the live app surface.

Phase `28` remains the current umbrella donor-audit target.
Inserted Phase `28.1` now captures the bounded RTK-sidecar thread discovered during that donor reading.
It is intentionally a go/no-go audit, not an automatic implementation order.

Settled baseline before execute:

- Phase `27` closed as selective `hermes-lcm` host-level donor uptake
- Phase `27.1` closed as correct Bestie mirroring plus a narrow measured diagnostics win
- no broader retrieval-quality lift was proven in `27.1`
- donor freshness alone is **not** enough reason to ship code
- the RTK-sidecar question is now explicitly separated into:
  - runtime wiring truth
  - bounded value proof
  - explicit no-op if the gain is not real

Current donor reading for the next thread:

- Hindsight:
  - strongest immediate candidate
  - likely around bounded retrieval-budget discipline
- MemPalace:
  - likely audit-only unless backend-boundary leakage is found
- Graphiti:
  - explicit no-op unless the audit finds a concrete runtime-ROI delta
- RTK:
  - relevant only as a bounded sidecar-shaping input
  - not a direct donor port target
  - first question is whether the local sidecar should do anything beyond budget/persist telemetry

The current recommended next threads are therefore:

- Phase `28`:
  - targeted upstream donor delta audit and selective refresh
- Phase `28.1`:
  - bounded RTK-sidecar runtime wiring and value audit

Neither thread authorizes blanket donor sync or a broad host-side rewrite.

Phase `21` is execution-complete at gate.
It restored Brainstack-only ownership of personal memory / communication-contract behavior on a clean deployed-path proof and closed the deeper seam without falling back to persona/skill-file patching.
Phase `20.8` is execution-complete.
Phase `20.9` established valid patched-runtime answer-only truth but not a clean closing split proof.
Phase `20.10` is execution-complete and hardened the benchmark workflow itself.
Phase `20.11` is execution-complete at gate.
Its cheap structural donor-first retrieval scope produced real generic wins, but the residual `gpt4_7f6b06db` temporal-event relevance gap is now handed off to `20.12` as a capability-phase rather than more `20.11` micro-tuning.
Phase `20.12` is execution-complete at gate.
It proved a bounded temporal semantic rerank layer and an env-gated external scorer path, but the residual `gpt4_7f6b06db` miss remained upstream of scorer strength: the relevant trip temporal-event rows still did not reliably surface into the bounded live pool.
Phase `20.13` is execution-complete at gate.
It proved that the dominant upstream blocker was benchmark-path session mixing plus undersized per-flush generation windows, landed a bounded session-boundary benchmark seeding fix, and restored the desired trip-chain generation in oracle-only session-aligned proof. The remaining `gpt4_7f6b06db` miss is now better read as temporal chain coverage / final selection breadth over now-available events rather than scorer-vs-availability confusion.
Phase `20.14` is execution-complete at gate.
It closed the temporal chain coverage handoff with a bounded selection-layer rebalance:
- temporal bucket diversity in selection
- no reuse of already selected temporal rows across `recent` / `matched`
- no cap increase required for the named bounded proof
Phase `20.15` is execution-complete at gate.
It closed the bounded aggregate capability question with a combined win:
- stronger Tier-2 typed entity extraction now writes aggregate-capable graph structure
- one bounded native Kuzu aggregate sum path now surfaces a real `native_aggregate` row over the benchmark-derived graph state
- the decisive blocker after the first implementation pass was planner/query shape mismatch against live typed entity shapes, not total absence of structure
- completed spillover read before `20.16` scope lock:
  - the `70`-item oracle retrieval-only spillover confirms that the `20.11–20.15` structural fixes generalize well beyond the fixed canary set
  - final oracle metrics:
    - `fact/fact`: `31`
    - `aggregate/aggregate`: `21`
    - `temporal/temporal`: `17`
    - `temporal/fact`: `1`
    - `memory_context_present`: `70 / 70`
    - `backend_population_nonzero`: `48 / 70`
    - `zero_backend_cases`: `22 / 70`
    - `empty_text_batches`: `19`
    - `zero_backend` overlapped `empty_text` in `19` cases
  - the stronger current reading is that this oracle residual class is primarily a benchmark-runner artifact:
    - `--oracle-seed` restricts to answer-session IDs
    - short answer-only sessions are more exposed to default `turn_interval` flush behavior
    - the wider oracle run used the default benchmark flush shape rather than the stronger `session_boundary + 900` proof configuration
  - the smaller `12`-item live retrieval-only spillover, however, finished much healthier:
    - `fact/fact`: `5`
    - `aggregate/aggregate`: `4`
    - `temporal/temporal`: `3`
    - `memory_context_present`: `12 / 12`
    - `backend_population_nonzero`: `12 / 12`
    - `zero_backend_cases`: `0`
    - `empty_text_batches`: `0`
  - the best current reading is therefore:
    - the structural fixes are real and live-bridge health is not collapsing on the checked live slice
    - the `70`-oracle zero-backend class should not be treated as a proven product-path blocker
    - the remaining oracle-specific short-session admission behavior is worth carrying forward as an edge-case note, not as the main `20.16` thread

Latest measured `20.9` live truth after explicit runtime-parity correction:

- local `20.9` validation:
  - `44 passed`
- critical correction:
  - the first `20.9` live reruns were partially invalid because they ran against a stale Bestie runtime
  - patched source parity was then reinstalled into the Bestie plugin runtime and rechecked before the valid rerun
- valid comparable live answer-only on the patched runtime:
  - `5 / 15`
  - suspicious answer-judge passes: `2`
- valid answer-only route-source distribution:
  - `deterministic_route_hint`: `14 / 15`
  - `default`: `1 / 15`
- valid answer-only applied-mode distribution:
  - `fact`: `8`
  - `temporal`: `5`
  - `aggregate`: `2`
- valid answer-only activated-route yield:
  - temporal nonzero yield: `3 / 5`
  - temporal zero yield: `2 / 5`
  - aggregate nonzero yield: `1 / 2`
  - aggregate zero yield: `1 / 2`
- full comparable split rerun:
  - not accepted as final phase truth
  - repeated runs produced partial / unstable artifacts instead of one clean closing report

Interpretation standard for the current state:

- no Brainstack component should be accepted under a \"not buggy\" or \"good enough\" label
- each component must be treated as:
  - correct for the current phase contract
  - explicitly pending with a named gap
  - or wrong and fixed now
- the current routing gate is therefore tracked as a calibrated `20.3` iteration decision with explicit bounds, not as a fuzzy acceptable compromise
- LongMemEval is a calibration probe, not the product objective
  - the real target is a SOTA Hermes memory kernel:
    - coherent continuous conversation
    - proactive stateful continuity
    - long-range accurate recall and relation-tracking
    - usable storage of large bodies of knowledge
    - meaningful token savings
  - benchmark-specific benchmaxing drift is explicitly disallowed

Explicit pending gaps after `20.9`:

- runtime-sync truth is now a first-class blocker
  - stale Bestie runtime distorted `20.9` measurements again
  - every future harness or benchmark run needs an explicit source-vs-target parity check before execution
- live fact-path parity remains badly unresolved
  - old strongest decomp-off historical reference: `10 / 15`
  - current valid comparable answer-only on patched runtime: `5 / 15`
- route-hint reliability is no longer the main excuse
  - deterministic replacement is live on the patched runtime
  - the remaining route-policy gap is classifier correctness and downstream route quality
  - the documented live misroute family is now larger than the original `20.8` audit set because `f523d9fe` emerged as an additional false-positive temporal case in valid `20.9` live runs
- structural route activation is real, but activation still does not imply quality
  - activated temporal routes with nonzero yield: `3 / 5`
  - activated temporal routes with zero yield: `2 / 5`
  - activated aggregate routes with nonzero graph yield: `1 / 2`
  - activated aggregate routes with zero graph yield: `1 / 2`
  - candidate quality and evidence packing remain unresolved on activated structural routes
- profile / identity retrieval remains a named unresolved class
  - `5d3d2817`
- the current full split benchmark loop is too slow / unstable to remain the default diagnostic inner loop
  - comparable split truth for `20.9` did not close cleanly
  - the next phase must first harden the harness strategy before more large retrieval-fix loops
- any future fail-open widening must stay explicitly bounded
  - bounded multi-channel fusion / soft routing remains the named fallback if the deterministic gate hurts more than it helps
  - unbounded \"dump more rows\" fallback is explicitly disallowed
- aggregate counting remains opportunity-cost warning only
  - not a hard score ceiling
  - not the dominant objective of the next phase
- exact-value supersession remains recorded technical debt with later ownership
  - important
  - but not the immediate next cut
- `20.10` has now delivered:
  - runtime-sync verification as mandatory step `0`
  - retrieval-quality harness via runner `--retrieval-only`
  - fixed canary subset support via runner `--canary`
  - route-harness cleanup with explicit `f523d9fe` audit support
  - full `15`-question live reruns removed from the default inner loop
- actual `20.10` validation truth:
  - runtime-sync check against the current Bestie root compared `28` files and found `0` mismatches
  - deterministic route-harness sanity on canary + extra case completed with `6` results
  - targeted local validation passed:
    - `22 passed`
    - `py_compile` clean on `4` modified files
- `20.10` intentionally does **not** claim retrieval-quality improvement
  - it is a validation/harness phase, not a retrieval-recovery phase
  - the next retrieval phase should consume the new fast-feedback ladder instead of returning to full `15`-question inner-loop reruns
  - the first `20.11` step should therefore be a runtime-sync-passing, patched-runtime `--retrieval-only --canary` baseline reading before any new retrieval code change
  - this should be treated as required pre-change ground truth, not optional smoke-test
  - a local checkpoint commit of the `20.10` harness state is recommended before `20.11` retrieval changes begin, even if nothing is pushed yet
- actual `20.11` baseline instrument reading has now completed on patched runtime:
  - runtime sync:
    - `ok: true`
    - `compared_files: 28`
    - `mismatch_count: 0`
  - canary retrieval harness:
    - `5 / 5` completed
    - elapsed: `344.904s`
    - `memory_context_present: 5 / 5`
    - non-fact routes: `2 / 5`
- `20.11` baseline findings already narrow the next work:
  - `c8c3f81d` remains the stable fact baseline
  - `5d3d2817` remains a live profile / identity retrieval miss even though direct debug proved relevant transcript rows exist in storage
  - `e9327a54` is now a confirmed fact-path packing win in the patched canary
  - `gpt4_7f6b06db` now activates `temporal` cleanly in the live canary, so the old blocker is no longer route-policy contamination
  - `6c49646a` shows that the aggregate route is not blank on patched runtime because graph yield is nonzero (`6`)
- additional `20.11` follow-up tightened that reading further:
  - a real half-wired live-path crash was found and fixed:
    - `db.py` referenced `profile_priority_adjustment(...)` without importing it
  - a source/runtime route-policy drift was found and fixed:
    - the source had drifted back to the LLM route-hint path instead of the recorded bounded deterministic default
    - the deterministic default resolver is now restored in source and resynced to Bestie
  - a generic transcript-row prioritization patch produced one real live win:
    - `e9327a54` now surfaces `turn 50` / Sugar Factory first in the patched canary transcript block
  - a later bounded carry-through / budget rebalance pass improved `5d3d2817` further:
    - a structural continuity-to-transcript carry-through join bug was identified and fixed
      - continuity and transcript rows for the same turn did not share raw `id`, so the join now keys on `session_id + turn_number`
    - the final live packed memory block now contains the answer-bearing marketing-specialist transcript row (`turn 126`) alongside the later senior-marketing-analyst row (`turn 128`)
    - the targeted patched-runtime retrieval harness now answers this case correctly
    - therefore the case is no longer a pure carry-through miss; the remaining blocker is residual junk suppression / packing around a now-present answer-bearing row
  - the restored patched canary rerun also reset the route reading:
    - runtime sync still held (`28` compared files, `0` mismatch)
    - route source distribution is now:
      - `deterministic_route_hint`: `4 / 5`
      - `default`: `1 / 5`
    - non-fact routes are back to `2 / 5`
      - `gpt4_7f6b06db` now runs `temporal`
      - `6c49646a` now runs `aggregate`
  - `gpt4_7f6b06db` is now a cleaner diagnostic case:
    - live structural channels are nonblank (`temporal: 10`, `graph: 4`)
    - packed evidence is still off-target
    - targeted current-debug now suggests the actual trip rows are largely absent from the fused pool
    - therefore the remaining blocker is better described as temporal candidate generation / extraction first, then downstream packing
  - the completed latest canary retrieval-only rerun now has a stable runtime profile:
    - `5 / 5` completed
    - elapsed: `303.93s`
    - `memory_context_present: 5 / 5`
    - non-fact routes: `2 / 5`
  - a later post-join-fix canary retrieval-only rerun tightened the truth again:
    - runtime sync still held (`28` compared files, `0` mismatch)
    - `5 / 5` completed in `318.259s`
    - `5d3d2817` now answers correctly in retrieval-only mode and carries the answer-bearing `turn 126` marketing-specialist transcript row in the final live memory block
    - `gpt4_7f6b06db` still runs cleanly as `temporal` with nonzero structural counts (`temporal: 14`, `graph: 8`), but its final live memory block still misses the actual trip set
    - targeted current-debug further shows the true trip rows are largely absent from the fused pool, not merely dropped at the last packing step
    - therefore the current leading unresolved blocker was moved upstream from pure carry-through into structural temporal retrieval on activated non-fact routes
- one bounded temporal shortlist experiment was tried and then reverted:
  - a strict relevance-shortlist-then-chronology selection variant for temporal rows made `gpt4_7f6b06db` worse by promoting generic “past three months” fitness/stamps rows
  - the patch was reverted immediately after the targeted live rerun
  - this is now explicit negative evidence against naive lexical/semantic shortlist tightening on the temporal path
- a second bounded temporal query-form experiment was also tried and then reverted:
  - a route-aware focused-search-query variant for temporal retrieval made `gpt4_7f6b06db` worse by shifting transcript evidence toward Kyoto / attachment junk
  - the patch was reverted immediately after the targeted live rerun
  - this is now explicit negative evidence against naive temporal query shaping / frame-token stripping on the current signal set
- a third bounded temporal search-limit experiment was also tried and then reverted:
  - a temporal-route widening of continuity / transcript / semantic candidate-pool limits increased raw channel counts
  - but the targeted live rerun still selected the same off-target turns (`matched: 25, 37, 35`; `transcript: 37, 38, 35`)
  - the real Muir Woods / Big Sur / Yosemite trip set still did not surface
  - this is now explicit negative evidence against bounded search-pool widening over the current retrieval signals
- a donor-first structured temporal-event path is now also in source and locally validated:
  - Tier-2 can emit bounded `temporal_events` tied to real transcript `turn_number`s
  - reconciliation persists them as `temporal_event` continuity rows with temporal metadata
  - the source-targeted suite stayed green (`48 passed`) and the plugin-namespace real-world flow suite passed (`25 passed`)
- the first targeted patched-runtime reruns after that temporal-event path still do **not** prove live retrieval recovery on `gpt4_7f6b06db`:
  - the answer string may come back correct
  - but the captured memory context still omits `Muir Woods`, `Big Sur`, and `Monterey`
  - therefore the result must be read as unsupported answer recovery, not retrieval success
- the new parser-context logging also narrowed one ambiguity:
  - live `Tier2 extractor returned non-JSON payload` failures were observed on unrelated batch windows such as `turns=[89..96]`, `turns=[185..192]`, and `turns=[270..277]`
  - so Tier-2 JSON truncation is a real reliability issue
  - but it is not yet proven to be the direct cause of the specific trip-order miss
- a later benchmark-path Tier-2 telemetry pass tightened the diagnosis again:
  - the benchmark runner was confirmed to use unusually fat seed settings by default:
    - `flush interval = 96`
    - `transcript limit = 192`
  - under that default `96/192` seed path, `gpt4_7f6b06db` produced:
    - `batch_count: 3`
    - `parse_status_counts: {"non_json": 1, "json_object": 2}`
    - `batches_with_writes: 2`
    - `total_writes: 19`
    - graph population only `entity=2`, `state=0`, `relation=0`, `inferred=1`
  - a bounded `32/32` rerun improved structural population materially:
    - `batch_count: 9`
    - `parse_status_counts: {"non_json": 6, "json_object": 3}`
    - `batches_with_writes: 3`
    - `total_writes: 32`
    - graph population improved to `entity=3`, `state=2`, `relation=1`, `inferred=1`
    - live route channels improved to `graph: 4`, `temporal: 10`
  - but the final selected evidence still stayed off-target for the trip-order question
  - a follow-up `32/32/900` probe then ruled out the simplest truncation story:
    - `parse_status_counts` degraded from `{"non_json": 6, "json_object": 3}` to `{"non_json": 7, "json_object": 2}`
    - `total_writes` dropped from `32` to `14`
    - so merely raising Tier-2 `max_tokens` is now explicit negative evidence, not the fix
  - therefore the current best blocker statement is now:
    - seed-time Tier-2 reliability / structural population instability first
    - downstream temporal candidate quality / packing second
- therefore `20.11` should not jump to canary answer-only yet
  - the retrieval-only baseline already exposes concrete retrieval defects worth fixing first
- the current forward-looking architectural reading is now also explicit:
  - short-term improvement should come from temporal extraction / candidate yield, better packing, and bounded grounding carry-through after retrieval quality improves
  - the `5d3d2817` truth now implies an important implementation split:
    - the answer-bearing profile evidence now survives into the final live memory block after the structural join fix
    - so the current cheap internal fusion / packing fixes and a future asymmetric reranker / stronger-embedder layer are both attacks on the same junk-suppression problem
    - the present phase should keep trying the cheaper internal path first because it is directly testable on the patched canary loop
    - a reranker / stronger-embedder path is still a valid next-phase capability candidate if the cheap internal path stalls
  - medium-term aggregate recovery likely needs stronger Tier-2 typed entity extraction plus a bounded native Kuzu aggregate query path
  - any future reranker / embedder phase should be recorded at the capability level first
    - stronger asymmetric reranking for profile / identity and asymmetric question-to-statement retrieval
    - stronger semantic retrieval backbone only if the cost/reindex/runtime story is explicit
    - do not prematurely lock this to a single named vendor/model family in `STATE`
  - tentative brand-level note:
    - if a named embedder candidate must be tracked already, the current strongest recorded external candidate is the Jina v5 text-embedding family served through a TEI-style path
    - this is based on current public model-card positioning, not on an in-repo bakeoff result
    - therefore it remains a soft candidate, not a hard rule
  - this is not yet treated as a proven score ceiling or guarantee; it is the strongest current architectural candidate for the aggregate-counting class
  - planning-doc hygiene note:
    - `STATE.md` and `ROADMAP.md` are now large enough that latest-phase orientation is getting slower
    - this is not a current runtime or retrieval blocker, so it must not interrupt `20.11`
    - but a future compact-state artifact (`STATE-COMPACT.md` or equivalent) should be created once the current retrieval critical path clears
    - the goal is faster access to current truth without deleting the append-only historical record
  - temporal-selection performance note:
    - the `20.14` temporal diversity helper currently uses extra linear passes plus repeated chronology parsing / sorting
    - this is not a current blocker because the active temporal pools are still small
    - if temporal-event pools later become much larger, optimize there first:
      - cache parsed temporal anchors
      - reduce repeated chronological sorts
      - reduce repeated row copying during diversity selection

## Current Truth
- Latest Hermes host supports one external memory provider alongside the built-in provider.
- Built-in prompt memory can be functionally disabled with:
  - `memory_enabled: false`
  - `user_profile_enabled: false`
- Built-in `memory` tool is now removed from the live tool surface whenever no built-in memory store is active.
- The correct host-facing architecture is one composite provider, not three peer memory providers.
- User priority is effectively tied at the top between:
  - agent smartening / continuity
  - token savings
  - graph / temporal truth
- Large corpus handling is a very close second priority, not a low-priority follow-up.
- The user wants full displacement of Hermes built-in memory behavior and built-in user profile handling.
- Future architecture questions must be asked in non-technical language with enough explanation to support an informed decision.
- Personal identity, preferences, and shared work continuity should live on a separate stable shelf.
- The first real version should launch with broad scope rather than a deliberately narrow pilot.
- The default control philosophy should prioritize maximum token savings.
- Early architecture should include real integration surfaces for RTK and My-Brain-Is-Full-Crew, not only abstract future placeholders.
- On memory conflicts, the system should surface the conflict and ask rather than silently choosing a winner.
- Responses should mention their basis by default, but not noisily; provenance should become more explicit when confidence is low or the case is important.
- The system should prefer best-effort answers with explicit uncertainty over bluffing or hard abstention by default.
- For medical and study use, the primary emphasis is on connections and explanation, while still preserving accuracy and fast retrieval.
- Old states should be preserved alongside newer states so temporal change remains visible instead of destructive overwrite.
- The corpus layer should aim for deep integration of the full corpus, not shallow search-only handling.
- Personal preferences should be learned strongly and applied by default.
- The desired overall character is primarily an agent-like personality, secondarily a study companion and assistant.
- The desired operations model is highly automatic with little manual maintenance, but contradictions should be surfaced explicitly.
- Brainstack now has Brainstack-owned temporal normalization and point-in-time helpers instead of implicit temporal behavior scattered across call sites.
- Brainstack now has Brainstack-owned provenance normalization and merge behavior, with bounded provenance rendering available for important or uncertain recall.
- Graph truth recall now prefers current state by default, surfaces prior state only when it materially helps, and shows open conflicts explicitly instead of flattening them.
- The Phase `20` flat `3 / 15` final-boss result is now treated as a memory-fidelity blocker, not as an architecture blocker.
- The post-`20.1` final-boss rerun reached `9 / 15`, which confirms the donor-first recovery direction is materially working but not yet sufficient for the original proof bar.
- The remaining gap is now best described as a targeted exact-fact conversational retrieval problem, not as a broad architecture problem.
- Query decomposition is recorded as a lever for true multi-entity misses, but not as a universal cure for all remaining failures.
- Single-topic failures like charity totals are recorded as fact-seeking retrieval precision problems rather than decomposition problems.
- Exact-value update preference remains a recorded gap: fresher corrected numeric facts still need stronger supersession preference over older values.
- If query decomposition is used in `20.2`, it should be a single bounded auxiliary step that both decides and emits sub-queries, not a two-step classifier-plus-decomposer chain.
- The preferred `20.2` execution order is now recorded as: packing fidelity, fact-seeking ranking, user-fact grounding, exact-value supersession preference, then bounded query decomposition.
- The `20.2` rerun regression must now be analyzed as at least three retrieval problem families, not one:
  - simple exact-fact recall
  - aggregate/exhaustive recall
  - temporal/timestamp-ordered recall
- The current benchmark discussion now records that recall class comes before grounding class:
  - if the right evidence is absent, stronger prompt grounding cannot rescue the answer
- The benchmark is now explicitly recorded as a diagnostic instrument, not the product goal:
  - the goal remains a more accurate and more useful everyday kernel
  - benchmark-only overlays should be treated skeptically unless they generalize beyond the benchmark
- The LongMemEval dataset mix is now measured rather than guessed:
  - `26.6%` multi-session
  - `26.6%` temporal-reasoning
  - `15.6%` knowledge-update
  - only the remainder is simpler single-session retrieval
- This measured mix is now recorded as evidence that ranking-only tuning is unlikely to be the full long-term answer.
- The immediate `20.2` forensic route is now explicitly locked:
  1. rerun with `query_decomposer=None`
  2. keep every other `20.2` lever unchanged in that first rerun
  3. if needed, ablate the new candidate-priority bonuses next
  4. only then decide what remains truly architectural
- The first pure `20.2` A/B forensic rerun has now completed:
  - post-`20.1`: `9 / 15`
  - post-`20.2` bundle: `7 / 15`
  - post-`20.2` with `query_decomposer=None`: `10 / 15`
- This now counts as strong evidence that bounded query decomposition was the primary regression lever in the first `20.2` bundle.
- Disabling decomposition recovered these regressed cases:
  - `6c49646a`
  - `d682f1a2`
  - `gpt4_7f6b06db`
- Remaining regressions versus the `9 / 15` post-`20.1` baseline:
  - `0db4c65d`
  - `f523d9fe`
- Therefore the next forensic target is no longer decomposition first:
  - decomposition should stay disabled by default for now
  - the next A/B pass should inspect the remaining bonus/ranking overlays
- The second pure `20.2` A/B forensic rerun has also completed:
  - decomposition still disabled
  - `digit` + quote bonuses removed together
  - result: `3 / 15`
- This now proves that the pair (`digit` + quote) is not safe to ablate together in the current decomposition-off configuration.
- The post-`3 / 15` grounding discussion is now recorded with stricter epistemic wording:
  - dangerous retrieval/grounding coupling is a fact
  - the stronger `authoritative` wording as the primary specific cause is still only a hypothesis
  - a separate wording-only A/B would be required to prove that claim
- Therefore the bonus forensics must now split those two levers apart:
  - quote-off alone
  - digit-off alone
  - only then revisit `user-led`
- The quote-off-only third A/B pass has now completed:
  - decomposition still disabled
  - quote removed
  - `digit` and `user-led` retained
  - result: `5 / 15`
- This now proves the quote bonus is also load-bearing in the current exact-fact retrieval configuration.
- Therefore the best currently proven configuration remains:
  - decomposition disabled
  - quote restored
  - digit restored
  - `user-led` unchanged
- The digit-off-only fourth A/B pass has now completed:
  - decomposition still disabled
  - `digit` removed
  - quote and `user-led` retained
  - result: `7 / 15`
- This now proves the `digit` bonus is also load-bearing, though less strongly than quote.
- The full bonus-forensics matrix is now closed:
  - decomp off, quote on, `digit` on -> `10 / 15`
  - decomp off, quote off, `digit` on -> `5 / 15`
  - decomp off, quote off, `digit` off -> `3 / 15`
  - decomp off, quote on, `digit` off -> `7 / 15`
- Not every `20.2` bonus is now treated as equally suspect:
  - `digit` and quote bonuses remain suspect, but can no longer be treated as disposable local overlays
  - `user-led` priority remains epistemically plausible, but likely needs a smaller weight if it survives the second pass
- The wording-only grounding A/B has now also completed:
  - decomposition still disabled
  - quote / `digit` / `user-led` retained
  - evidence-priority wording softened from `authoritative` to `prefer strongly`
  - result: `6 / 15`
- This now proves the stronger grounding wording is also load-bearing in the current exact-fact stack.
- The low-cost `20.2` forensic cycle is therefore closed.
- The current best proven baseline remains:
  - decomposition disabled
  - quote on
  - `digit` on
  - `user-led` on
  - stronger grounding wording intact
  - score `10 / 15`
- The local overlay stack is now explicitly interpreted as compensatory rather than fundamentally strong:
  - all four local levers are load-bearing inside the present stack
  - but the net gain over the post-`20.1` baseline is still only `+1` (`9 / 15` -> `10 / 15`)
  - therefore the current quote / `digit` / grounding overlay layer should be treated as mutual compensation over deeper retrieval limits, not as proof of a solved architecture
- Beyond that, the remaining gap points primarily at structural temporal / aggregate retrieval rather than more bonus or wording tuning.
- The earlier candidate numbering that mentioned `20.3 / 20.4 / 20.5` as possible residual slices is now retired for clarity.
- The next real roadmap phase is now a single clean `20.3`:
  - Structural Retrieval Routing For Temporal, Aggregate, And Fail-Open Intent-Aware Queries
- This numbering cleanup matters because the next work is not more local `20.2`-style tuning shards.
- It is a new structural retrieval phase with one coherent contract.
- The current long-term retrieval direction is now recorded as query-intent-aware executive retrieval, with distinct modes for:
  - relevance retrieval
  - exhaustive/aggregate recall
  - timestamp-ordered retrieval
- Bounded multi-entity decomposition is now recorded as a helper lever that may feed those modes, not as the universal retrieval path.
- The next structural retrieval phase must not inherit the current decomposition gate/path as-is:
  - simple fact mode should remain decomposition-free by default
  - temporal and aggregate paths should be designed directly, not routed through the current decomposition logic
  - any future decomposition should return only as a narrowly justified helper for true multi-entity queries under a new design
- The longer-term routing target is now explicitly fail-open rather than a hard exclusive classifier:
  - temporal-first / aggregate-widened / relevance-first routing may bias retrieval
  - but generic fallback must remain so a wrong intent guess does not zero out recall
- Phase `20.2` execution is complete and recorded in `phases/20.2-high-precision-conversational-fact-retrieval-recovery/20.2-01-SUMMARY.md`.
- Phase `20.2` tightened exact-fact retrieval without reopening architecture work:
  - boundary-aware transcript / continuity packing
  - fact-priority conversational ranking bonuses
  - stronger user-fact evidence wording
  - bounded exact-value auto-supersession on the existing graph-state path
  - optional one-call bounded decomposition with a `3` sub-query cap
- The current exact-value auto-supersession in `db.py` is now recorded as temporary technical debt:
  - acceptable to keep short-term for correctness
  - not acceptable as the final donor-first boundary
  - long-term update/supersession intent should move toward Tier-2 / reconciler signaling rather than remain a shell-side permanent rule
- The Brainstack code-review graph DB is healthy even though some CRG routes timed out:
  - `list_graph_stats_tool` and full-detail `get_review_context_tool` worked
  - the observed instability is route-specific, not a broken index or missing graph build
- Operational note from the first pure `20.2` A/B rerun:
  - the Bestie checkout `.venv` had `openai` but not `kuzu`
  - the valid real-path rerun therefore used `/home/lauratom/Asztal/ai/hermes-agent-port/venv/bin/python` against the Bestie checkout
  - this is an environment/runtime detail, not a Brainstack source regression
- Phase `20.1` execution is complete and recorded in `phases/20.1-benchmark-exposed-memory-fidelity-recovery/20.1-01-SUMMARY.md`.
- Conversation transcript history can now be published into the existing `Chroma` semantic backend and retrieved through the live semantic channel, instead of leaving conversation semantics corpus-only.
- Imported/history turns can now preserve explicit event timestamps through `sync_turn()` and the continuity/transcript write path, so temporal rendering no longer depends only on ingestion-time timestamps.
- Transcript evidence defaults and control-plane ceilings are now wider, and transcript/continuity rendering is date-rich and less aggressively clipped.
- The legacy regex role-ingress path has been removed from the old graph extractor so the known junk `role=...` truth family can no longer enter graph context through that route.
- The memory wrapper and contract now say that specific, non-conflicted recalled facts outrank generic prior knowledge, without introducing a blind “always trust memory” rule.
- The LongMemEval seed path now explicitly enables the donor-aligned `Kuzu` + `Chroma` backends and preserves provided session dates as imported event time.
- Phase `20.1` corrective priority order is now locked as:
  - conversational semantic indexing
  - temporal/date-rich rendering
  - graph quality gate
  - transcript evidence widening
  - adaptive evidence packing
  - evidence-priority prompt rule
- `20.1` should target a significant benchmark jump, but must not pre-commit to a specific final score before the corrected mini-proof exists.
- Phase 13 live proof passed on the installed Bestie runtime for current-only recall, temporal history recall, conflict surfacing, and bounded basis display.
- Brainstack now boosts same-session identity, preference, and shared-work rows so fresh communication-style facts can affect the next unrelated follow-up without waiting for a later semantic match.
- In Brainstack-only mode, personal profile/style/identity memory remains exclusively Brainstack-owned, while `skill_manage` stays available for reusable procedural workflows.
- Brainstack-only host behavior now suppresses automatic skill nudges while still allowing explicit procedural skill use.
- Graph reconciliation now normalizes named-user relations over the generic `User` alias once identity is known, reducing duplicate personal graph facts.
- Phase 14.2 live proof passed on the installed Bestie runtime for fast preference application, scoped `skill_manage` blocking, procedural skill allowance, and `User` → named-user relation canonicalization.
- Brainstack now records bounded retrieval telemetry for surfaced profile and graph rows inside existing `metadata_json`, instead of adding a new scoring subsystem.
- Phase 15 uses Brainstack-owned usefulness helpers and modest shelf-aware ranking adjustments, not a flat donor ratio transplant.
- Repeated fallback-only non-core profile rows can now be gently deprioritized without deletion, while identity, preference, and shared-work rows remain protected.
- Phase 15 live carry-through was briefly masked by a machine reboot during rebuild; a direct force-recreate compose rebuild closed the gap and confirmed the new telemetry code is present in the running Bestie container.
- Phase 15 verify-work is complete and recorded in `15-UAT.md`.
- Current Codex CLI runtime is not reliable for subagent-driven GSD execution; planning and execution must avoid depending on subagent calls until that runtime issue is fixed.
- Phase 1 now has a GSD-compliant executable plan at `01-01-PLAN.md`.
- Phase 1 now has a local single-agent research artifact at `01-RESEARCH.md`.
- Phase 1 now also has an implementation-facing contract artifact at `01-IMPLEMENTATION-CONTRACT.md`.
- Phase 2 now has a GSD-compliant executable plan at `02-01-PLAN.md`.
- Brainstack now has a real local continuity/profile provider slice at `plugins/memory/brainstack/`.
- The Brainstack Phase 2 slice uses hook-based delivery and exposes no model-facing tools by default.
- Phase 2 targeted E2E tests pass via `uv run --extra dev python -m pytest tests/agent/test_memory_plugin_e2e.py`.
- Phase 2 verify-work passed and is recorded in `02-UAT.md`.
- Phase 3 now has a GSD-compliant executable plan at `03-01-PLAN.md`.
- Brainstack now has a graph-truth slice with entities, relations, temporal states, supersession links, and surfaced conflicts.
- Phase 3 targeted E2E tests pass via `uv run --extra dev python -m pytest tests/agent/test_memory_plugin_e2e.py`.
- Phase 3 verify-work passed and is recorded in `03-UAT.md`.
- Phase 4 now has a GSD-compliant executable plan at `04-01-PLAN.md`.
- Brainstack now has a corpus slice with explicit document ingestion, section storage, and bounded section-aware recall.
- Phase 4 targeted E2E tests pass via `uv run --extra dev python -m pytest tests/agent/test_memory_plugin_e2e.py -q`.
- Phase 4 verify-work passed and is recorded in `04-UAT.md`.
- Phase 5 now has a GSD-compliant executable plan at `05-01-PLAN.md`.
- Brainstack now has a working-memory control plane with explicit query analysis, dynamic shelf budgets, provenance escalation, and bounded tool-avoidance policy.
- Phase 5 targeted E2E tests pass via `uv run --extra dev python -m pytest tests/agent/test_memory_plugin_e2e.py -q`.
- Phase 5 verify-work passed and is recorded in `05-UAT.md`.
- Phase 6 now has a GSD-compliant executable plan at `06-01-PLAN.md`.
- Hermes now removes the built-in `memory` tool from the live tool surface whenever no built-in memory store is active.
- Built-in memory guidance, flush behavior, and memory-review triggers now stay off in the displaced Brainstack path, and stray built-in memory calls fail closed.
- Phase 6 targeted host tests pass via `uv run --extra dev python -m pytest tests/run_agent/test_brainstack_native_memory_displacement.py -q`.
- Phase 6 verify-work passed and is recorded in `06-UAT.md`.
- Permanent native retirement still requires verification acceptance of the executed Brainstack replacement coverage / native contract matrix and the anti-half-wire audit.
- Phase 06.1 exists as the explicit Brainstack replacement coverage gate before any final native retirement claim.
- Phase 06.1.1 exists as the mandatory AI wiring audit / anti-goal-drift gate before later integrations build on false assumptions.
- Phase 06.1 execution is complete and recorded in `06.1-01-SUMMARY.md`, `06.1-NATIVE-CONTRACT-MATRIX.md`, and `06.1-COVERAGE-REPORT.md`.
- Phase 06.1.1 execution is complete and recorded in `06.1.1-01-SUMMARY.md`, `06.1.1-AI-WIRING-AUDIT.md`, and `06.1.1-GOAL-DRIFT-REPORT.md`.
- Phase 06.1.1 verify-work is complete and recorded in `06.1.1-UAT.md`.
- Phase 06.2 exists as a bounded real-world proving gate between wiring proof and donor-layer integrations.
- Phase 06.2 execution is complete and recorded in `06.2-REAL-WORLD-REPORT.md` and `06.2-01-SUMMARY.md`.
- Phase 06.2 verify-work is complete and recorded in `06.2-UAT.md`.
- Phase 7 now has a GSD-compliant executable plan at `07-01-PLAN.md`.
- RTK now has a real bounded sidecar slice in `agent/rtk_sidecar.py` that tightens tool-output budgets without taking memory ownership.
- `run_agent.py` now applies RTK budget policy at the existing tool-result persistence and turn-budget enforcement points.
- Phase 7 targeted RTK sidecar tests pass via `python -m py_compile agent/rtk_sidecar.py && uv run --extra dev python -m pytest tests/run_agent/test_rtk_sidecar_integration.py tests/run_agent/test_brainstack_integration_invariants.py tests/run_agent/test_run_agent.py::TestExecuteToolCalls::test_result_truncation_over_100k -q`.
- Phase 7 verify-work is complete and recorded in `07-UAT.md`.
- Phase 8 now has a GSD-compliant executable plan at `08-01-PLAN.md`.
- My-Brain-Is-Full-Crew now has a bounded shell slice in `agent/mbifc_shell.py`.
- `run_agent.py` now injects the My-Brain-Is-Full-Crew shell block through the existing system prompt path when enabled in config.
- Phase 8 targeted shell tests pass via `python -m py_compile agent/mbifc_shell.py && uv run --extra dev python -m pytest tests/run_agent/test_mbifc_shell_integration.py tests/run_agent/test_run_agent.py::TestBuildSystemPrompt::test_includes_mbifc_shell_prompt_when_enabled -q`.
- Phase 8 verify-work is complete and recorded in `08-UAT.md`.
- Full `hermes-lcm` adoption is intentionally rejected for now; only its transcript/compaction pattern is allowed as a donor inside Brainstack.
- Phase 9 now has a GSD-compliant executable plan at `09-01-PLAN.md`.
- Brainstack now has an append-only transcript shelf for raw turns and bounded snapshot entries in addition to the existing continuity/profile/graph/corpus shelves.
- The transcript shelf is injected only as bounded fallback evidence; it does not create a second context engine or new model-facing tool surface.
- Phase 9 targeted transcript and regression tests pass via `python -m py_compile plugins/memory/brainstack/transcript.py plugins/memory/brainstack/db.py plugins/memory/brainstack/__init__.py plugins/memory/brainstack/retrieval.py plugins/memory/brainstack/control_plane.py tests/agent/test_brainstack_transcript_shelf.py && uv run --extra dev python -m pytest tests/agent/test_brainstack_transcript_shelf.py tests/agent/test_memory_plugin_e2e.py tests/agent/test_brainstack_real_world_flows.py tests/run_agent/test_brainstack_integration_invariants.py -q`.
- Phase 9 verify-work is complete and recorded in `09-UAT.md`.
- Phase 9 security review is complete and recorded in `09-SECURITY.md`.
- Transcript retrieval is now explicitly session-local, and high-stakes transcript suppression is covered both by policy and explicit regression assertions.
- Phase 10 now exists as the explicit middle-ground modularity / update-safety phase between the current baked-in donor state and any later full one-click donor update architecture.
- Phase 10 now has a GSD-compliant context and executable plan at `10-CONTEXT.md`, `10-PLAN.md`, and `10-01-PLAN.md`.
- Phase 10 execution is complete and recorded in `10-01-SUMMARY.md`, `10-DONOR-BOUNDARY-MATRIX.md`, and `10-REFRESH-WORKFLOW.md`.
- Phase 10 verify-work is complete and recorded in `10-UAT.md`.
- Phase 10 security review is complete and recorded in `10-SECURITY.md`.
- Brainstack donor-backed continuity, graph, and corpus substrate paths now run through explicit local adapter seams and a structured donor registry under `plugins/memory/brainstack/donors/`.
- The bounded donor refresh entrypoint now exists at `scripts/brainstack_refresh_donors.py` and can honestly report local donor baselines plus compatibility smoke results without claiming upstream auto-merge.
- The donor refresh entrypoint now fails closed for unknown donor keys and rejects adapter paths that escape the repo root.
- Phase 10 targeted donor-boundary verification passes via `uv run --extra dev python -m pytest tests/agent/test_brainstack_donor_boundaries.py tests/agent/test_brainstack_transcript_shelf.py tests/agent/test_memory_plugin_e2e.py tests/run_agent/test_brainstack_integration_invariants.py -q`.
- Phase 10 bounded refresh smoke passes via `python scripts/brainstack_refresh_donors.py --run-smoke --strict`.
- Brainstack replacement contract tests and anti-half-wire integration invariants pass via `uv run --extra dev python -m pytest tests/run_agent/test_brainstack_replacement_contract.py tests/run_agent/test_brainstack_integration_invariants.py tests/run_agent/test_brainstack_native_memory_displacement.py tests/agent/test_memory_plugin_e2e.py -q`.
- Pragmatic real-world scenario coverage now also passes via `uv run --extra dev python -m pytest tests/agent/test_brainstack_real_world_flows.py tests/run_agent/test_brainstack_replacement_contract.py tests/run_agent/test_brainstack_integration_invariants.py tests/run_agent/test_brainstack_native_memory_displacement.py tests/agent/test_memory_plugin_e2e.py -q`.
- The code-review-graph MCP full postprocess build path now runs in background successfully for the Hermes repo, so graph-backed audits can be used without blocking on the previous timeout failure.
- The first post-`v3.0.0` MemPalace release materially improved packaging, protocol negotiation, SQLite/WAL hygiene, deterministic IDs, and test coverage; for future donor work it should be treated as a stronger corpus baseline than the earlier snapshot reviewed during initial stack selection.
- Milestone `v2.0 Hermes Brainstack` is archived in `.planning/milestones/v2.0-ROADMAP.md` and `.planning/milestones/v2.0-REQUIREMENTS.md`.
- The active roadmap is intentionally collapsed after milestone completion; future work should start from a fresh milestone definition instead of appending into the archived one.
- Milestone `v2.1 Brainstack Profile Intelligence` now targets a layered profile extraction pipeline with explicit Tier-1, Tier-2, and write-policy seams.
- The next milestone intentionally prioritizes safer, smarter preference learning over full donor auto-update automation.
- The chosen architectural order is: mini modularization first around profile extraction, then Shiba-style Tier-2 inference (strictly debounced and batched at session-end to guarantee high ROI and protect LLM API token costs), then safety/proving.
- Before Phase 11, Brainstack needs an Integration Kit because the fresh Docker/Discord Bestie runtime can be a correct Hermes Gateway while still missing `plugins/memory/brainstack`.
- The chosen upstream-update strategy is Brainstack-native integration plus an idempotent install/update/doctor workflow, not API-first as the first production path and not a long-lived Hermes fork.
- Brainstack's core/store should remain API-ready for a later sidecar, but the primary runtime path remains native Hermes MemoryProvider integration.
- Installer and doctor flows must fail closed when upstream Hermes lifecycle/provider surfaces are incompatible instead of silently creating a half-wired runtime.
- Phase 10.1 execution is complete and recorded in `10.1-01-SUMMARY.md`.
- Brainstack now has install/update/doctor scripts in `/home/lauratom/Asztal/ai/atado/Brainstack/scripts/`.
- The fresh Docker Bestie runtime checkout at `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest` now contains `plugins/memory/brainstack/` and selects `memory.provider: brainstack`.
- The Bestie Docker build context now excludes runtime/config/state artifacts via `.dockerignore`, which fixes rebuild failures caused by container-owned runtime files under `hermes-config/`.
- The Bestie Docker healthcheck now validates `/proc/1/cmdline` instead of relying on missing `pgrep`, so the running gateway reports `healthy` instead of a false `unhealthy`.
- Host doctor checks pass against the fresh Bestie runtime; container-level provider import also resolves to `brainstack`.
- The Brainstack integration kit now supports both `docker` and `local` runtime modes through the same installer/doctor/update flow.
- Docker-mode installs now also generate `scripts/hermes-brainstack-start.sh` in the target Hermes checkout for simple `start`, `rebuild`, `full`, `stop`, `status`, and `logs` operations.
- Practical Discord smoke on the fresh Bestie runtime proved the current Brainstack durable-write path is still too noisy for production use.
- The current durable-write bug is input-hygiene oriented, not a speaker-mixing bug: pasted technical analyses and quoted transcript/doc blobs from user messages are being mistaken for durable profile facts.
- Graph and corpus shelves remain structurally present but practically underfed in live usage; they should not be patched by growing language-specific regex coverage.
- The project now explicitly rejects further language-specific regex expansion as the long-term path; the correct direction is Tier-0 hygiene first, then explicit ingest slots, then Tier-2 multilingual extraction and reconciliation.
- Phase 10.2 now has a GSD-compliant context and executable plan at `10.2-CONTEXT.md` and `10.2-01-PLAN.md`.
- Phase 10.2 execution is complete and recorded in `10.2-01-SUMMARY.md`.
- Phase 10.2 now blocks durable profile noise through a Brainstack-owned Tier-0 guardrail with explicit rejection reasons.
- Phase 10.2 installed-runtime smoke proof passed on the installed Bestie plugin path using a temporary SQLite DB because the live container-owned DB file is host-readonly.
- Phase 11 now has a GSD-compliant context, plan, and execution summary at `11-CONTEXT.md`, `11-01-PLAN.md`, and `11-01-SUMMARY.md`.
- Phase 11 execution is complete: Tier-1 extraction now lives outside the provider, ingest planning is explicit, and the Tier-2 scheduling seam exists without a second runtime.
- Phase 13 has two preferred donor candidates already identified for later planning:
  - `kernel_memory_temporal.py` for temporal normalization and point-in-time effectiveness checks
  - `kernel_memory_provenance.py` for provenance normalization and multi-source merge
- Phase 11 should explicitly define a debounce / scheduling seam for Tier-2 work instead of letting Tier-2 fire on every turn.
- Phase 12 should explicitly follow an extractor → reconciler → write-policy pattern; extraction without reconciliation is considered architecturally incomplete.
- Phase 15 now exists as the later adaptive usefulness-scoring / retrieval-telemetry step after Phase 14 proving, not as an early shortcut.
- The donor `kernel_memory_feedback_priority.py` is useful inspiration for later telemetry, but its flat ratio scoring should not be treated as the final Brainstack model.
- Phase 14.1 now exists as a bounded graph-backed anti-half-wire audit after Phase 14; it should stay practical and must not become an oversized test program.
- A future Phase 16 now exists to revisit and significantly strengthen Layer 2 because the current knowledge graph is still not strong enough for the intended product.
- Phase 16 must treat `https://github.com/itsXactlY/neural-memory` as inspiration only for implicit relation discovery ideas, not as a transplantable architecture.
- Phase 16 now keeps Mnemosyne as narrow retrieval/L2 inspiration only; `keep` has been explicitly de-scoped so the project does not drift toward a larger skill+notes platform shape.
- Phase 14 execution is complete and recorded in `14-01-SUMMARY.md`.
- Phase 14.1 execution is complete and recorded in `14.1-01-SUMMARY.md`.
- The installed Bestie gateway no longer relies on a process-only Docker healthcheck; readiness now depends on truthful gateway status and real platform connectivity.
- `gateway_state.json` in the live runtime now clears stale failure fields correctly and reports per-platform connection state instead of preserving contradictory old error data across restarts.
- The readiness-aware gateway health contract is now carried by the Brainstack integration kit, not only by the currently patched Bestie checkout.
- The latest live smoke proved that Brainstack now persists identity, project context, communication preferences, and graph relations materially better than before, but immediate behavioral application is still too loose.
- `skill_manage` should remain available for procedural workflow learning, but it must not be allowed to own personal profile, style, or identity memory in Brainstack-only mode.
- The next correctness step is not a full `skill_manage` ban; it is a scoped ownership boundary plus faster preference application and deduplication/normalization of user identity records.
- The generated Docker helper now has a real conversational `purge` / `reset` path that clears session replay files under `/opt/data/sessions/` in addition to Brainstack/state DBs, so clean-room testing no longer leaves hidden session persistence behind.
- The Brainstack installer now tolerates both the current single-line Hermes import seams and the known multiline upstream variants for the `gateway/run.py` platform import and the `run_agent.py` memory-manager import, reducing future refresh drift without speculative wider patching.
- Live post-15 Discord testing exposed a remaining host-side ownership leak: Brainstack-only mode can still steer personal preference capture toward `skill_view`, `skill_manage`, `read_file`, and `write_file` workflows even when Brainstack correctly owns the memory itself.
- The next correction is therefore not in Layer 2 yet; it is a bounded host/runtime hardening step to close personal-memory tool detours before the L2 redesign continues.
- Phase 15.1 now has a GSD-compliant context and executable plan at `15.1-CONTEXT.md` and `15.1-01-PLAN.md`.
- Phase 15.1 execution is complete and recorded in `15.1-01-SUMMARY.md`.
- Phase 15.1 verify-work is complete and recorded in `15.1-UAT.md`.
- Phase 16 now has a GSD-compliant context and executable plan at `16-CONTEXT.md` and `16-01-PLAN.md`.
- Phase 16 is explicitly broader than “better extraction”; it is the L2 architecture phase for:
  - truth-class separation
  - bounded implicit relation discovery
  - stronger L2 retrieval
  - cleaner graph recall packaging
- Mnemosyne remains only a narrow internal retrieval/L2 inspiration for Phase 16, not a transplant, and benchmark posture is not a development target.
- Phase 16 execution is complete and recorded in `16-01-SUMMARY.md`.
- Brainstack L2 now stores bounded inferred relations separately in `graph_inferred_relations` instead of flattening them into explicit truth.
- `search_graph()` now ranks graph rows by truth class, overlap, confidence, and bounded retrieval telemetry instead of simple row-type priority plus recency.
- Graph recall packaging now separates:
  - `Current Truth`
  - `Open Conflicts`
  - `Historical Truth`
  - `Inferred Links`
- Tier-2 extraction and reconciliation now support optional bounded `inferred_relations` without changing the overall runtime model.
- Matching explicit relations now shadow equivalent inferred links so inferred recall does not compete with explicit truth.
- Phase 16 targeted source validation passed with `28 passed`.
- Phase 16 live carry-through passed on the installed Bestie runtime, including proof that inferred-link code is present in the container and explicit relations rank ahead of inferred ones in recall.
- Phase 16 verify-work is now complete and recorded in `16-UAT.md`.
- Phase 16 user verdict is effectively `pass with caveat`:
  - explicit truth stays primary
  - historical truth and inferred links may surface when useful
  - but they must not displace current explicit truth or present themselves as equally certain
- There is now an explicit strategic recovery track after Phase 16:
  - `16.1` donor re-centering audit
  - `16.2` modularization recovery and glue reduction plan
  - `17` Layer-1 continuity/smartening restoration
  - `18` Layer-2 knowledge-graph restoration
  - `19` Layer-3 corpus/packing restoration
  - `20` real-world proof and restoration verdict
- The recovery track exists because the current Brainstack is working, but has drifted away from the original donor-first "big 3 plus thin glue" vision.
- During this recovery window, new feature growth is no longer the default; donor truth audit and glue reduction come first.
- A Brainstack-specific 15-case LongMemEval subset now runs end-to-end through the real Hermes/Brainstack path and scored `3/15` (`0.20`) in `392.4s`; this is now the hard baseline proving that donor re-centering and modularization recovery are necessary, not optional.
- Phase `16.1` donor audit is now complete and explicitly concludes that Brainstack currently behaves more like a strong integration shell with diluted donor memory strength than like the original “big 3 plus thin glue” vision.
- Phase `16.1` now hard-freezes the recovery window under these rules:
  - no new memory feature work
  - no new Brainstack-owned heuristics as donor-strength replacement
  - no benchmark-gaming
  - no MVP acceptance for `16.2/17/18/19/20`
- The `16.1` audit records these donor-specific truths:
  - `Hindsight` strength is only partially restored; continuity exists, but the originally desired cross-session smartening is still too weak.
  - `Graphiti` strength is only partially restored; temporal graph correctness exists, but graph usefulness is still below the intended donor ambition.
  - `MemPalace` strength is only partially restored; corpus seams and bounded packing exist, but donor-level corpus retrieval advantage is not yet convincingly restored.
- The `16.1` audit also records which Brainstack-owned responsibilities remain justified:
  - ownership
  - orchestration
  - safety
  - packaging
  - installer / doctor / host integration
- Phase `16.2` modularization recovery is now complete and records a concrete file-level contract for:
  - keep local
  - thin down
  - donor-recenter
  - stop growing
- The `16.2` contract explicitly keeps these modules in the Brainstack shell role:
  - `db.py`
  - `temporal.py`
  - `provenance.py`
  - `stable_memory_guardrails.py`
  - donor registry / adapter seam
  - installer / doctor / host payload ownership boundary
- The `16.2` contract explicitly marks these areas as donor-recovery pressure points:
  - `tier1_extractor.py` for `17`
  - `graph.py` and `tier2_extractor.py` for `18`
  - `corpus.py` for `19`
- The `16.2` contract now explicitly rejects temporary legacy alignment as the end state for `17`; donor-restored L1 behavior must become the primary path, not a bridge layered around the old heuristic path.
- Phase `17` discuss is now explicitly closed on these points:
  - donor-first hybrid retrieval becomes the primary L1 path, not a fallback
  - the intended hybrid minimum is:
    - vector similarity
    - FTS / keyword search
    - temporal signal
  - handwritten language-specific trigger lists and regex-driven extraction growth are treated as fatal multilingual drift, not acceptable engineering tradeoffs
  - the success bar is donor-level smartening on the donor’s own domain, not “better than before”
  - the eval ladder must include:
    - fast Brainstack-adapted acceptance scenarios
    - a small smartening-focused suite
    - a small LongMemEval subset
    - final boss LongMemEval only at the end
- The architecture split is now clarified in plain language:
  - Brainstack owns the shell:
    - shell state
    - host boundaries
    - cross-store ingest consistency
    - safety
    - packaging
    - installer / doctor / update-safe integration
  - donors own the memory intelligence
  - truth / time / provenance should end up primarily Graphiti-shaped rather than permanently living as Brainstack-local intelligence
- The accepted embedded donor-backend picture is now:
  - `L1` = Hindsight/TEMPR-style executive retrieval intelligence
  - `L2` = Graphiti-shaped graph/truth with `Kuzu` as the default embedded backend target
  - `L3` = MemPalace-style raw corpus retrieval with `Chroma` as the default embedded backend target
  - `SQLite` remains only for shell/session/profile/transcript state, not as the engine for all memory intelligence
- Large-corpus ingest is now explicitly expected to require batched, rate-limited, resumable L2 extraction during cross-store ingest, and this is treated as a shell orchestration responsibility rather than a separate architectural subsystem.
- The `16.2` contract explicitly marks these local modules as seams that must be thinned rather than allowed to keep absorbing donor weakness:
  - `control_plane.py`
  - `retrieval.py`
  - `usefulness.py`
  - `extraction_pipeline.py`
- Phase `17` now has a GSD-compliant executable plan at `17-01-PLAN.md`.
- The `17` plan locks these implementation truths:
  - L1 must become a distinct Hindsight/TEMPR-style executive retrieval layer
  - L1 must run through an explicit channel contract:
    - semantic
    - keyword / FTS
    - graph
    - temporal
  - current graph and corpus seams must be rebound behind that contract so later `18/19` backend restoration does not force another L1 redesign
  - `tier1_extractor.py` must stop being the effective center of live smartening behavior
  - `control_plane.py`, `retrieval.py`, and `usefulness.py` must thin down instead of hiding weak donor recall with local glue
- The recovery track is now explicitly hard-rule and anti-MVP:
  - donor-strength gaps must not be “solved” with new local heuristics
  - `16.2/17/18/19/20` are judged against the original donor-first ambition, not against a weaker “better than before” baseline
  - module retention must be justified under ownership/orchestration/safety/packaging/host-integration, or it should be thinned or removed
- Brainstack-only host behavior now blocks Hermes side-memory file detours for personal memory (`~/.hermes/notes`, Hermes-root `MEMORY.md`, Hermes-root `USER.md`) instead of letting user-profile/style capture escape into note/file workflows.
- `run_agent.py` in Brainstack-only mode now carries explicit ownership guidance that personal identity, preferences, communication style, and project context belong in Brainstack, while procedural skills remain allowed.
- Phase 15.1 live proof passed for:
  - installer + doctor carry-through
  - rebuilt Docker runtime
  - live container presence of the new guidance and file boundary
  - `blocked_notes = True`
  - `allowed_proc = True`
  - gateway status `running; connected=discord`
- Phase `20.6` execution is complete and recorded in `phases/20.6-live-restoration-for-fact-parity-route-graph-and-profile-retrieval/20.6-01-SUMMARY.md`.
- `20.6` proved that the installed Bestie plugin really did have a half-wired stale `executive_retrieval.py`, and that mismatch has now been repaired.
- `20.6` also proved that the live route-hint path was failing on MiniMax response shape:
  - empty `message.content`
  - non-empty `message.reasoning_content`
  - too-small route-hint token budgets
- After the `20.6` repair, live structural routing is no longer effectively dead:
  - answer-only `route_source=direct_benchmark_route_hint`: `13 / 15`
  - split `route_source=direct_benchmark_route_hint`: `12 / 15`
  - answer-only non-fact applied modes: `6 / 15`
  - split non-fact applied modes: `4 / 15`
- `20.6` also disproved the earlier “mostly empty graph backend” story as the main current blocker:
  - answer-only backend population:
    - `SQLite` graph nonzero: `14 / 15`
    - `Kuzu` graph nonzero: `14 / 15`
    - `Chroma` nonzero: `15 / 15`
  - split backend population:
    - `SQLite` graph nonzero: `12 / 15`
    - `Kuzu` graph nonzero: `12 / 15`
    - `Chroma` nonzero: `15 / 15`
- `20.6` live restoration still failed badly after those repairs:
  - answer-only: `3 / 15`
  - split raw answer score: `2 / 15`
  - split `retrieval_correct`: `2 / 15`
  - split `both_correct`: `1 / 15`
- `20.6` therefore must be interpreted as:
  - successful live wiring repair
  - failed live restoration
- `20.6` preserved and sharpened two named failure classes:
  - `5d3d2817` = profile / identity retrieval miss on the live fact path
  - `d682f1a2` = retrieval-correct / answer-wrong grounding leak
- `20.6` also exposed a separate execution-path anomaly class:
  - `6a1eabeb`
  - `gpt4_7f6b06db`
  - blank route metadata plus missing `<memory-context>` block in the captured prompt

## Accumulated Context

### Roadmap Evolution
- Phase 06.1 inserted after Phase 6: Brainstack replacement coverage native contract matrix (URGENT)
- Phase 06.1.1 inserted after Phase 06.1: AI wiring audit and anti-goal-drift gate (URGENT)
- Phase 06.2 inserted after Phase 06.1.1: pragmatic real-world E2E memory proving (URGENT)
- Phase 09 inserted after Phase 8: Hindsight lossless transcript hardening
- Phase 10 inserted after Phase 9: structured donor boundary and refresh workflow
- Phase 10.1 inserted after archived Phase 10 as a v2.0.1 stabilization detour: Brainstack Integration Kit and upstream Hermes update workflow
- Phase 10.2 inserted after Phase 10: Tier-0 noise filtering and ingest hygiene
- Phase 14.1 inserted after Phase 14: graph-backed wiring audit and anti-half-wire gate
- Phase 14.2 inserted after Phase 14.1: preference application and skill boundary hardening (URGENT)
- Phase 15 added: Adaptive memory usefulness scoring and retrieval telemetry
- Phase 16 added: Layer-2 graph enrichment and implicit relation discovery
- Phase 23 added: Broader deployed-live conversational quality and coverage validation
- Phase 27.1 inserted after Phase 27: Bestie mirror and measured validation for selective hermes-lcm donor uptake (URGENT)
- Phase 29 added: live communication-contract recall and post-reset durability forensics
- Phase 29.1 inserted after Phase 29: canonical communication contract and durable identity capture hardening (URGENT)
- Phase 29.2 inserted after Phase 29: practical logistics memory capture and reminder boundary audit (URGENT)
- Phase 29.4 inserted after Phase 29.3: oracle regression runner repair and pre-forensics gate (URGENT)
- Phase 42.1 inserted after Phase 42: final-output typed invariant enforcement and fail-closed obedience (URGENT)
- Phase 48 added: live chat authority bootstrap, enforcement, recall, and gateway stabilization
- Phase 52 added: native user-profile re-anchoring, Brainstack kernel-only recovery, and file-level keep/demote/remove/rebuild map
- Phase 53 added: live multi-session Discord UAT, reset proof, and product-readiness correction loop
- Phase 54 added: native explicit truth atomicity, Discord surface precedence, and explicit pack persistence recovery
- Phase 55 added: Discord explicit rule-pack fidelity, ordinary-turn compliance, and final live proof
- Phase 57 added: live Discord stuck-run recovery, fail-closed runtime containment, native scheduler truth, and reset leak cleanup
- Phase 60 added: Brainstack-universal real-world usage audit and temporal/provenance correction from a live Discord case study
- Phase 65 added: PullPhase 1 post-refactor traceable hybrid retrieval fusion
- Phase 66 added: PullPhase 2 post-refactor global working-memory allocator and packet budgeter
- Phase 67 added: PullPhase 3 post-refactor wiki corpus source through bounded corpus ingest
- Phase 68 added: PullPhase 4 post-refactor Hermes stable extension seams and installer patch reduction
- External memory donor source map added: `.planning/research/external-memory-donor-source-map.md`
- Phase 70 added: Brainstack agent-facing memory tool surface
- Phase 71 added: Brainstack provider lifecycle and MCP/operator UX
- Phase 72 added: Brainstack explicit durable capture contract
- Phase 73 added: Brainstack bounded memory maintenance lifecycle
- Phase 74 added: Brainstack session and procedure memory read-model
- Phase 75 added: Brainstack bounded associative expansion and activation ranking
- Phase 76 added: Brainstack product-grade corpus ingest substrate
- Phase 77 added: Brainstack multilingual and multimodal proof gate
- Phase 70-77 are now planned with `70-01-PLAN.md` through `77-01-PLAN.md` and are constrained by `IMMUTABLE-PRINCIPLES.md` plus `.planning/research/external-memory-donor-source-map.md`.
- Phase 67/76 strengthened with derived-index and corpus fingerprint drift detection so stale embedder/parser/chunker/schema state cannot look green.
- Phase 70 strengthened with model-facing allowlist vs operator/debug-only tool split so MCP availability does not imply normal model-callability.
- Phase 71 strengthened with provider/MCP shared-state concurrency, resync, and degraded-state requirements.
- Phase 77 strengthened so competitor-readiness scorecards require local proof or explicit unsupported/deferred labels, not README claims.
- Phase 57 is now complete in source-of-truth and reproduced on the installed `finafina` runtime.
- Phase 57 closeout truth:
  - graph/provider failure paths now fail closed instead of staying half-open
  - bare `Session reset.` no longer leaks through the installed gateway runtime
  - reminder creation is now fail-closed at scheduler-core level for past one-shot schedules
  - cron delivery no longer disappears as fake one-shot success when delivery fails
  - real Discord delivery proof was captured by creating live proof jobs and reading them back from the target Discord thread with the live bot token
- Phase 29.1 execution is now complete and recorded in `29.1-01-SUMMARY.md`.
- Phase 10.2 completed with bounded installed-runtime smoke proof and no language-specific regex growth.
- Phase 11 completed with explicit Tier-0/Tier-1/Tier-2 scheduling seams and targeted anti-half-wire verification.
- Phase 13 verify-work is complete and recorded in `13-UAT.md`.
- Phase 14 execution is complete and recorded in `14-01-SUMMARY.md`.
- Brainstack everyday-memory proving now covers ordinary follow-up, shared-work recall, relationship recall, and corrected-current-state behavior instead of only synthetic shelf tests.
- A deeper host half-wire family was closed in the installed Bestie runtime:
  - legacy `memory` and `session_search` tool paths are removed in Brainstack-only mode
  - session reset / resume / expiry now route through Brainstack-aware finalization
  - maintenance agents no longer carry legacy memory toolsets in Brainstack-only mode
- The Brainstack integration kit now carries the same host-side fix into fresh Hermes checkouts through installer payload + recognized host patches + doctor checks, instead of relying on one manually patched runtime.
- Workspace boundaries are now explicitly documented in `.planning/WORKSPACE-BOUNDARIES.md` so Brainstack source, GSD planning, and live runtime work do not drift across folders silently.
- Phase 14.2 execution is complete and recorded in `14.2-01-SUMMARY.md`.
- Post-execute live testing showed that Phase 14.2 still has an unresolved read/backflow/privacy bug cluster.
- The canonical note for that is `phases/14.2-preference-application-and-skill-boundary-hardening/14.2-ROOT-CAUSE-NOTES.md`.
- The rejected direction is further heuristic growth; the preferred direction is read-path contract hardening, private recall packaging, and retrieval-time collapse of overlapping style rows.
- A structured handoff now exists in `.planning/HANDOFF.json` and `phases/14.2-preference-application-and-skill-boundary-hardening/.continue-here.md`.
- The non-heuristic 14.2 follow-up has now been implemented and recorded in `14.2-02-SUMMARY.md`.
- Phase 14.2 verify-work is complete and recorded in `14.2-UAT.md`.
- Phase 31 added: Post-30.6 regression forensics and cross-agent root-cause convergence
- Phase 32 added: Canonical contract protection, multi-message convergence, and sequential-path tool blocking hotfix

## Chosen Core Stack
- Hindsight
- Graphiti
- MemPalace

## Chosen Roles
- Hindsight = recency and continuity
- Graphiti = graph and temporal truth
- MemPalace = corpus/document storage and packing
- Mira-inspired control plane = working-memory orchestration and token discipline

MemPalace donor note:
- Prefer the latest upstream MemPalace state as the default corpus donor baseline.
- Reuse it through adapter seams rather than hard-forking internals into Brainstack.

## Non-Core / Optional
- RTK = early token-efficiency sidecar
- NeuronFS = donor ideas only
- My-Brain-Is-Full-Crew = recommended first as early upper skill / workflow shell, with a later path to stronger orchestration if earned
- Hermes PR #5641 = donor only, not foundation
- `sync_turn()` must remain non-blocking under Hermes plugin rules; slow extraction belongs in a provider-local background worker, not in the turn path.
- Phase 12 introduced a real Tier-2 extractor + deterministic reconciler path without adding a second runtime.
- The installed `hermes-bestie` image has already been rebuilt and live-proved with fake extraction:
  - non-blocking turn path
  - background worker completion
  - profile write
  - graph write
  - continuity summary / decision write
- Phase 17 execution is complete and recorded in `phases/17-layer-1-continuity-and-smartening-restoration/17-01-SUMMARY.md`.
- Phase 17 removed the handwritten Tier-1 path from the live L1 center and introduced `brainstack/executive_retrieval.py` as the donor-first executive retrieval seam.
- The semantic leg is now explicit and degraded-by-design until donor-backed vector retrieval lands; it is no longer silently faked through FTS.
- The remaining lexical lists in `brainstack/control_plane.py` are now explicitly treated as query-analysis policy hints, not as forbidden Tier-1 memory extraction heuristics; later donor-backed query classification may still replace them.
- A bounded Phase 17 eval ladder now exists in `scripts/run_brainstack_phase17_eval_ladder.py`.
- Per current workflow rules, live rebuild is not part of normal execution anymore; rebuild remains reserved for explicit test gates.
- Phase 17 verify-work is complete and recorded in `phases/17-layer-1-continuity-and-smartening-restoration/17-UAT.md`.
- Phase 18 execution is complete and recorded in `phases/18-layer-2-knowledge-graph-restoration/18-01-SUMMARY.md`.
- Phase 18 verify-work is complete and recorded in `phases/18-layer-2-knowledge-graph-restoration/18-UAT.md`.
- Layer 2 now has a real embedded graph backend seam:
  - `brainstack/graph_backend.py`
  - `brainstack/graph_backend_kuzu.py`
- The active L2 graph read center is now the configured backend target (`Kuzu` by default), while SQLite remains the shell-side canonical mirror and publication source.
- The first store-agnostic cross-store publish journal now exists in `brainstack/db.py` and tracks per-target publication state for graph subgraph snapshots.
- Phase 18 added SQLite → Kuzu bootstrap, failure/publish journal visibility, and richer Kuzu graph search that handles bidirectional expansion plus punctuated / inflected query tokens better than the initial backend slice.
- Phase 20.12 inserted after Phase 20.11: temporal-event semantic retrieval and reranking capability for structured continuity.
- Phase 20.13 inserted after Phase 20.12: upstream temporal-event candidate availability and generation reliability.
- Phase 20.14 execution is complete and recorded in `phases/20.14-temporal-chain-coverage-diversity-and-selection-cap-rebalance/20.14-01-SUMMARY.md`.
- Phase 20.14 closed the bounded temporal chain coverage handoff with a selection-layer rebalance:
  - temporal bucket diversity in temporal selection
  - non-reuse of already selected temporal rows across `recent` / `matched`
  - no cap increase required for the named trip-chain proof
- Targeted Phase 18 validation currently passes with `26 passed`.
- Installer and doctor were updated for the new graph backend defaults, but live carry-through into the Bestie checkout is currently blocked by a root-owned `hermes-config/bestie/config.yaml`; no rebuild and no push were performed.
- Phase 19 planning and execution are now recorded in:
  - `phases/19-layer-3-corpus-and-packing-restoration/19-CONTEXT.md`
  - `phases/19-layer-3-corpus-and-packing-restoration/19-01-PLAN.md`
  - `phases/19-layer-3-corpus-and-packing-restoration/19-IMPLEMENTATION-CONTRACT.md`
  - `phases/19-layer-3-corpus-and-packing-restoration/19-01-SUMMARY.md`
- Phase 19 restores the active L3 corpus center as:
  - embedded `Chroma` semantic corpus backend target
  - SQLite shell-side snapshot and lexical fallback
  - raw corpus retrieval as the primary L3 strength
  - bounded packing as a second-stage quality layer, not a retrieval rescue layer
  - extension of the existing store-agnostic journal core with `corpus.chroma` as a named publish target
- The L1 semantic corpus leg is no longer degraded-by-design; it now becomes active when the corpus backend is configured and healthy.
- Phase 19 introduced:
  - `brainstack/corpus_backend.py`
  - `brainstack/corpus_backend_chroma.py`
  - `scripts/run_brainstack_phase19_eval_ladder.py`
- Phase 19 targeted validation currently passes with:
  - Phase 19 eval ladder Gate A: `4 passed`
  - Phase 19 eval ladder Gate B: `2 passed`
  - extra regression suite: `7 passed`
- Installer and doctor now carry `corpus_backend: chroma` and `corpus_db_path`, but no live carry-through, rebuild, or push was performed during Phase 19 execution.
- Phase 19 verify-work is complete and recorded in `phases/19-layer-3-corpus-and-packing-restoration/19-UAT.md`.
- Phase 19 user verdict is a clear `pass` on the points that matter most:
  - stronger recall over larger prior material
  - genuinely live semantic corpus retrieval
  - broader recall without collapsing into unusable output
  - practical usefulness in ordinary conversation, not only in artificial corpus prompts

## Open Questions
- The remaining open question is no longer whether the named trip chain can be generated, restored, and preserved through final temporal selection under bounded proof.
- The stronger open capability question is now aggregate recovery at the donor-first architecture layer:
  - stronger Tier-2 typed entity extraction for non-generic events / transactions / trips
  - then a bounded native Kuzu aggregate query path for count / sum-style questions
- Temporal chronology quality may still matter in future broader temporal reasoning, but it is no longer the current critical-path blocker after `20.14`.

## Next Action
Use the `20.18` closeout as the new decision point before any further execute:

- `20.18` completed as a bounded live-surfacing phase, not a full live product pass
- the corrected isolated deployed Bestie reset eval now sits at:
  - `3 / 5`
  - report:
    - [brainstack-bestie-live-reset-eval-isolated.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase20/brainstack-bestie-live-reset-eval-isolated.json)
- what clearly improved:
  - `coffee_order` now passes on the degraded live stack
  - `gift_context` now passes on the degraded live stack
  - the `20.17` principal-scope isolation and noun-`order` route fixes remain intact
- what clearly remains:
  - `temporal_order` still fails as a low-overlap same-principal ordering miss
  - `aggregate_total` still fails because the live path is not using the earlier native aggregate capability
- the strongest current runtime truth is still:
  - deployed Bestie runs with `semantic` / `graph` degraded
  - therefore the current live ceiling is still dominated by the `keyword + temporal` stack
- because of that, the next thread should **not** be another blind degraded-stack micro-tuning pass
- the next GSD step should instead be:
  - execute the already planned follow-up phase for:
    - donor-aligned live graph/corpus backend enablement in deployed Bestie
    - then a post-enablement isolated live re-baseline
  - use that re-baseline to decide whether the remaining `temporal_order` miss survives once the intended runtime stack is actually live

Recommended next step: `/gsd-execute-phase 20.21`
Recommended effort: `xhigh`

## Phase 20.20 Planning Closeout

- `20.20` is now added and planned.
- planning files:
  - [20.20-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.20-enabled-stack-packet-bridge-native-aggregate-surfacing-and-live-stability/20.20-CONTEXT.md)
  - [20.20-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.20-enabled-stack-packet-bridge-native-aggregate-surfacing-and-live-stability/20.20-01-PLAN.md)
  - [20.20-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.20-enabled-stack-packet-bridge-native-aggregate-surfacing-and-live-stability/20.20-IMPLEMENTATION-CONTRACT.md)
- the phase is explicitly **not** a broader aggregate-expansion or fallback-stack tuning pass
- the planned reading is now:
  - `20.19` proved runtime graph/corpus activation
  - but did **not** prove stable final-packet dominance from enabled graph/corpus/native evidence
  - therefore the next honest thread is enabled-stack packet bridge + native aggregate surfacing + live stability
  - an important constraint for `20.20`: aggregate-mode native prepend already exists in the source, so the phase should prove and tighten that live path rather than invent a duplicate bypass
  - `graph_rows = 0` alone is not sufficient evidence against native graph surfacing, because `native_aggregate` rows currently surface through `matched`
- the phase is structured fail-closed:
  - diagnose where enabled graph/corpus loses influence before the final packet
  - land the smallest donor-aligned bridge hardening
  - prove native aggregate surfacing explicitly
  - then rerun the enabled-stack isolated live baseline
- if the bridge remains unstable or too broad, the contract allows an honest blocker closeout instead of a fake “fully integrated” claim

## Phase 20.20 Closeout

- `20.20` is execution-complete, but **not** gate-complete.
- summary:
  - [20.20-01-SUMMARY.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.20-enabled-stack-packet-bridge-native-aggregate-surfacing-and-live-stability/20.20-01-SUMMARY.md)
- touched code:
  - [executive_retrieval.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/executive_retrieval.py)
  - [test_brainstack_phase20_proof.py](/home/lauratom/Asztal/ai/atado/Brainstack/tests/test_brainstack_phase20_proof.py)
  - [executive_retrieval.py](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest/plugins/memory/brainstack/executive_retrieval.py)
- real bounded win:
  - aggregate route no longer hard-drops corpus rows
  - aggregate route support no longer ignores `graph_rows` / `corpus_rows`
  - source proofs now cover corpus-preserving aggregate routing and corpus-only aggregate support
- validation:
  - source proof slice: `4 passed`
  - Bestie regression slice: `20 passed`
  - focused live debug:
    - `reports/phase20/brainstack-20.20-live-debug.json`
  - post-patch isolated live baseline:
    - `reports/phase20/brainstack-bestie-live-reset-eval-isolated.json`
    - result: `4 / 5`
- honest live truth:
  - `aggregate_total` still passes without evidence of selected `native_aggregate`
  - focused live debug still shows `graph_rows = 0`, `corpus_rows = 0`, `has_native_aggregate = false`
  - the stronger `native_total_distance` proof still fails live (`510 miles` instead of `605`)
  - therefore the main residual is upstream live graph-native aggregate availability / production, not another small aggregate packet-weight tweak
- next thread:
  - add + plan `20.21`
  - focus on live typed graph-state / native aggregate availability and candidate carry-through on deployed Bestie

## Phase 20.21 Planning Closeout

- `20.21` is now added and planned.
- planning files:
  - [20.21-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.21-live-typed-graph-state-and-native-aggregate-availability-on-deployed-bestie/20.21-CONTEXT.md)
  - [20.21-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.21-live-typed-graph-state-and-native-aggregate-availability-on-deployed-bestie/20.21-01-PLAN.md)
  - [20.21-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.21-live-typed-graph-state-and-native-aggregate-availability-on-deployed-bestie/20.21-IMPLEMENTATION-CONTRACT.md)
- the phase is explicitly **not**:
  - degraded-stack micro-tuning
  - broader aggregate expansion
  - a new scorer/reranker branch
  - deploy packaging redesign
- the planned reading is now:
  - `20.19` activated live graph/corpus backends
  - `20.20` improved aggregate bridge logic in source/runtime
  - but live aggregate proofs still show no selected `native_aggregate` and `graph candidate_count = 0`
  - therefore the next honest thread is upstream live typed graph-state / native aggregate availability, not another packet-weight tweak
- the phase is structured fail-closed:
  - diagnose the first missing live aggregate-production seam
  - land only a bounded donor-aligned repair if the seam is local
  - require explicit native-aggregate live proof, not answer correctness alone
  - rerun isolated live baseline only if a meaningful availability fix lands
- if the required fix widens into a larger architectural availability project, the contract allows an honest blocker closeout instead of a fake “live graph solved” claim

## Phase 20.21 Closeout

- `20.21` is execution-complete at gate.
- summary:
  - [20.21-01-SUMMARY.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.21-live-typed-graph-state-and-native-aggregate-availability-on-deployed-bestie/20.21-01-SUMMARY.md)
- files touched:
  - Bestie runtime:
    - [run.py](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest/gateway/run.py)
  - Bestie tests:
    - [test_session_boundary_hooks.py](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest/tests/gateway/test_session_boundary_hooks.py)
- the bounded repair:
  - `/reset` now hands the warm cached agent to the background Brainstack finalize task before cache eviction
  - this preserves the provider instance that actually accumulated `_pending_tier2_turns`
- proof artifacts:
  - live graph availability proof:
    - `reports/phase20/brainstack-20.21-live-graph-availability-debug.json`
  - isolated deployed-live reset eval:
    - `reports/phase20/brainstack-bestie-live-reset-eval-isolated.json`
- validation:
  - gateway reset/finalize regression slice: `18 passed`
  - live graph availability proof shows:
    - `graph_entities = 4`
    - `graph_states = 12`
    - live recall `graph candidate_count = 9`
    - correct aggregate recall: `605 miles`
  - post-fix isolated deployed-live eval: `5 / 5`
- honest reading:
  - the main live aggregate-availability blocker was not Tier-2 schema quality by itself
  - it was the reset/finalize lifecycle seam dropping the warm provider instance before Brainstack session-end flush
  - after the repair, live graph-native evidence is materially present on deployed Bestie
  - the current evidence is strong enough that another immediate aggregate micro-phase would be overkill
- next step:
  - checkpoint current `20.17–20.21` live runtime gains
  - if continuing immediately in GSD, prefer broader deployed-live product validation / quality work over another aggregate micro-tuning phase

## Phase 20.22 Closeout

- `20.22` is execution-complete at gate.
- summary:
  - [20.22-01-SUMMARY.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.22-broader-deployed-live-product-validation-and-quality-truth/20.22-01-SUMMARY.md)
- planning files:
  - [20.22-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.22-broader-deployed-live-product-validation-and-quality-truth/20.22-CONTEXT.md)
  - [20.22-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.22-broader-deployed-live-product-validation-and-quality-truth/20.22-01-PLAN.md)
  - [20.22-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.22-broader-deployed-live-product-validation-and-quality-truth/20.22-IMPLEMENTATION-CONTRACT.md)
- broader deployed-live eval artifact:
  - `reports/phase20/brainstack-20.22-broader-deployed-live-eval.json`
- supporting truthful chain probe:
  - `reports/phase20/brainstack-20.21-chain-probe.json`
- initial wrong-path control artifact:
  - `reports/phase20/brainstack-20.22-provider-direct-control.json`
- broader truth after correcting the harness to the actual deployed provider/config path:
  - broader matrix result: `8 / 8`
  - category read:
    - coherent continuous conversation: `1 / 1`
    - stateful continuity after reset: `2 / 2`
    - long-range recall / relation-tracking: `4 / 4`
    - larger knowledge-body recall: `1 / 1`
- lightweight packet / token truth from the truthful chain probe:
  - selected rows:
    - `matched = 6`
    - `transcript_rows = 5`
    - `graph_rows = 3`
    - `corpus_rows = 0`
  - selected excerpt token estimate:
    - `552`
  - graph state remained materially present:
    - `interesting_state_count = 12`
    - aggregate answer: `605 miles`
- critical correction:
  - the first red `20.22` run was a harness mismatch, not product truth
  - the temp-home harness had forced `custom + MiniMax-M2.7`
  - the actual deployed Bestie config uses:
    - `provider: nous`
    - `model: xiaomi/mimo-v2-pro`
  - the `usage limit exceeded` artifact therefore belongs to the wrong-path control, not to the final deployed-live verdict
- honest reading:
  - `20.21` still stands as a real live runtime win
  - `20.22` now gives a healthy broader deployed-live quality read on the actual deployed path
  - no new dominant memory-kernel blocker surfaced in this phase
- next step:
  - checkpoint current `20.21–20.22` live truth
- if continuing immediately, prefer broader deployed-live quality/coverage validation rather than another narrow memory micro-phase

## Phase 21 Planning Closeout

- `21` is now added and planned.
- planning files:
  - [21-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/21-brainstack-only-memory-ownership-enforcement-communication-c/21-CONTEXT.md)
  - [21-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/21-brainstack-only-memory-ownership-enforcement-communication-c/21-01-PLAN.md)
  - [21-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/21-brainstack-only-memory-ownership-enforcement-communication-c/21-IMPLEMENTATION-CONTRACT.md)
- this phase exists because the manual deployed-live audit exposed a deeper class than simple memory miss:
  - Brainstack captures personal facts and style rules
  - but communication-contract rules do not reliably become live behavior
  - and assistant self-explanations can leak into durable memory truth
- explicit planning doctrine for this phase:
  - no band-aid persona strengthening as the default answer
  - no local patch before the ownership / prompt-layer / hygiene truth pass is complete
  - for each observed bug, check:
    - deeper shared seam
    - adjacent similar failure class
    - other affected modules before fixing
- the planned workstreams are:
  - ownership and prompt-layer truth audit before repair
  - deepest shared ownership-seam repair
  - communication-contract-to-behavior bridge repair
  - durable-memory hygiene repair
  - live rerun plus persisted-state inspection
- recommended immediate next step:
  - `/gsd-execute-phase 21`

## Phase 21 Closeout

- `21` is execution-complete at gate.
- summary:
  - [21-01-SUMMARY.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/21-brainstack-only-memory-ownership-enforcement-communication-c/21-01-SUMMARY.md)
- strongest new truths:
  - Brainstack-only ownership now holds on the personal memory / communication-contract axis on a clean temp home seeded from the deployed config/auth path
  - the deepest live seam was structured extraction on the real provider path:
    - `flush_memories` now requests structured JSON instead of depending on unconstrained reasoning text
  - communication-contract assembly is no longer dependent on brittle fuzzy graph-only lookup
  - explicit user communication rules that the live extractor can omit are now conservatively backfilled into stable communication slots from transcript evidence
  - durable-memory hygiene is tightened so assistant self-explanation and prompt/file/skill mechanics are not treated as profile/graph truth
- strict live artifact:
  - `reports/phase21/brainstack-phase21-live-rerun-strict.json`
  - final verdict:
    - `owns_personal_memory_axis = true`
  - persisted stable slots now include:
    - `preference:response_language`
    - `preference:ai_name`
    - `preference:communication_style`
    - `preference:emoji_usage`
    - `preference:message_structure`
    - `preference:pronoun_capitalization`
    - `preference:dash_usage`
- validation:
  - Brainstack Phase 21 source slice:
    - `10 passed`
  - Bestie Brainstack-only ownership slice:
    - `9 passed`
  - Bestie auxiliary structured-response / flush routing slice:
    - `4 passed`
- honest reading:
  - this is not a `persona.md`-strengthening fix
  - the owner is now Brainstack, while `SOUL.md` remains only a host compatibility shell
  - the right boundary is axis-specific:
    - Brainstack owns the personal-memory / communication-contract axis
    - native host capabilities remain legitimate outside that axis
    - the phase closed competing persistence/retrieval channels instead of trying to replace every native feature
  - `current_state_pairs = []` was audited as a non-blocking representation difference because profile rows, injected contract, and post-reset behavior still aligned on the owned contract
  - adjacent-similar detours were reproduced and closed in-phase:
    - `cronjob` automation detour
    - `execute_code` calling secondary-memory APIs like `plur_learn`
  - broader architecture read after closeout:
    - the cron boundary now looks correct:
      - native cron/automation remains legitimate
      - only personal-memory shadow-owner usage is blocked
    - `session_search` looks like a genuine coexistence candidate rather than a durable-memory owner:
      - it is an explicit transcript-forensics / session-browsing capability
      - hiding it wholesale in Brainstack-only mode may be over-displacement rather than clean ownership
    - the deeper host architecture still has one clarity gap:
      - legacy built-in memory lives directly in `run_agent.py`
      - plugin memory lives behind `MemoryManager`
      - current docs still imply a cleaner builtin+external layering than the runtime actually implements
- next step:
  - checkpoint Phase `21`
  - if continuing immediately, prefer broader deployed-live conversational quality / coverage validation over another personal-memory micro-phase

## Phase 22 Planning Closeout

- `22` has been added and planned.
- goal:
  - clarify the best long-term Brainstack/native boundary without over-displacing useful native features
- strongest planning truths:
  - cron/automation now appears correctly bounded:
    - native automation survives
    - only personal-memory shadow-owner usage is blocked
  - `session_search` is the strongest coexistence candidate:
    - likely transcript forensics / explicit session browsing
    - not obviously a durable personal-memory owner
  - host memory orchestration still has a clarity gap:
    - legacy built-in memory lives directly in `run_agent.py`
    - plugin memory lives behind `MemoryManager`
    - docs/runtime layering is not fully aligned
- explicit planning doctrine:
  - do not let Brainstack absorb native features just because they are memory-adjacent
  - classify by capability and ownership axis first
  - prefer thin boundary fixes over broad refactors
  - if execute reaches a real architecture fork, discuss it back to the user in simple language before locking the final direction
  - refreshed guardrails remain active:
    - donor-first
    - modularity / upstream updateability
    - truth-first
    - fail-closed on the owned axis
    - no benchmaxing
    - no overengineering
- planned files:
  - [22-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/22-brainstack-native-synergy-boundary-and-memory-orchestration-clarification/22-CONTEXT.md)
  - [22-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/22-brainstack-native-synergy-boundary-and-memory-orchestration-clarification/22-01-PLAN.md)
  - [22-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/22-brainstack-native-synergy-boundary-and-memory-orchestration-clarification/22-IMPLEMENTATION-CONTRACT.md)
- recommended next step:
  - `/gsd-execute-phase 22`

## Phase 22 Closeout

- `22` is execution-complete at gate.
- summary:
  - [22-01-SUMMARY.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/22-brainstack-native-synergy-boundary-and-memory-orchestration-clarification/22-01-SUMMARY.md)
- planning files:
  - [22-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/22-brainstack-native-synergy-boundary-and-memory-orchestration-clarification/22-CONTEXT.md)
  - [22-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/22-brainstack-native-synergy-boundary-and-memory-orchestration-clarification/22-01-PLAN.md)
  - [22-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/22-brainstack-native-synergy-boundary-and-memory-orchestration-clarification/22-IMPLEMENTATION-CONTRACT.md)
- final architecture verdict:
  - Brainstack keeps the durable personal-memory axis
  - `session_search` is a valid coexistence capability, not a competing personal-memory owner
  - native automation / `cronjob` should stay native outside the owned personal-memory axis
  - runtime/docs memory orchestration drift was real, but only required a thin clarity fix
- validation:
  - Bestie boundary regression slice: `10 passed`
  - Bestie memory-provider slice: `56 passed`
  - Phase `22` owned-file `ruff`: clean
  - Phase `22` owned-file `mypy`: clean
- next step:
  - return to broader deployed-live conversational quality / coverage validation

## Phase 22 Checkpoint

- `22` is now checkpointed.
- this checkpoint freezes the boundary decision:
  - Brainstack owns durable personal memory
  - `session_search` remains a bounded coexistence capability
  - `cronjob` remains native outside the owned axis
  - `MemoryManager` is documented as plugin-memory orchestration only
- the next recommended work should consume this boundary as settled baseline rather than reopening it by default

## Phase 23 Planning Closeout

- `23` has been added and planned.
- goal:
  - read broader deployed-live conversational quality and coverage honestly on top of the now-settled Brainstack/native boundary
- doctrine:
  - this is a product-truth phase, not another ownership phase and not default feature-building
- planned files:
  - [23-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/23-broader-deployed-live-conversational-quality-and-coverage-va/23-CONTEXT.md)
  - [23-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/23-broader-deployed-live-conversational-quality-and-coverage-va/23-01-PLAN.md)
  - [23-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/23-broader-deployed-live-conversational-quality-and-coverage-va/23-IMPLEMENTATION-CONTRACT.md)
- recommended next step:
  - `/gsd-execute-phase 23`

## Phase 23 Closeout

- `23` is execution-complete at gate as a validation phase.
- summary:
  - [23-01-SUMMARY.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/23-broader-deployed-live-conversational-quality-and-coverage-va/23-01-SUMMARY.md)
- broader live truth on the corrected deployed path:
  - scenarios: `10`
  - passed: `9`
  - accuracy: `0.9`
- category truth:
  - coherent continuous conversation: `2 / 2`
  - stateful continuity after reset: `2 / 2`
  - proactive stateful continuity: `0 / 1`
  - long-range relation-tracking: `4 / 4`
  - larger knowledge-body use: `1 / 1`
- the early `404` / `401` failures from this phase are now classified as harness-path mistakes, not product truth:
  - the Phase `23` runner initially misread the staged provider path
  - the final harness now resolves runtime provider settings the same way the real gateway does
- honest residuals:
  - proactive continuity after reset missed dietary carry-through
  - cross-principal profile bleed surfaced style/name/language durable items under unrelated principals
- architectural reading:
  - this does **not** reopen the Phase `22` boundary decision
  - Brainstack/native coexistence still reads as correct
  - the stronger next concern is principal-scoped durable profile hygiene plus narrower continuity carry-through quality
- recommended next step:
  - checkpoint Phase `23`
  - then add + plan a focused follow-up for:
    - principal-scoped durable profile isolation
    - proactive continuity carry-through hardening

## Phase 23 Checkpoint

- the `23` result is now the current broader deployed-live quality baseline
- this checkpoint freezes the current reading:
  - Phase `22` boundary remains valid
  - broader live conversational quality is mostly healthy at `9 / 10`
  - the remaining work is narrower than another broad validation phase
- the two named residuals to carry forward are:
  - principal-scoped durable profile isolation
  - proactive continuity carry-through hardening
- Shiba-style Tier-2 uplift remains a valid later capability thread, but not the immediate next priority:
  - partial Shiba-style elements already exist in Brainstack
  - the current first blocker is correctness / profile-scope hygiene
  - more aggressive Tier-2 preference/rule extraction before that fix risks amplifying the wrong durable state
- the next recommended work should consume Phase `23` as settled truth instead of re-arguing:
  - whether Brainstack/native coexistence was the right boundary
  - or whether the broader live quality phase itself was still only a harness artifact

## Phase 24 Planning Closeout

- `24` has been added and planned.
- goal:
  - close the two post-Phase-23 residuals without turning the work into a broad SHIBA uplift or a generic “smarter memory” phase
- planned files:
  - [24-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/24-principal-scoped-durable-profile-isolation-and-proactive-continuity-carry-through-hardening/24-CONTEXT.md)
  - [24-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/24-principal-scoped-durable-profile-isolation-and-proactive-continuity-carry-through-hardening/24-01-PLAN.md)
  - [24-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/24-principal-scoped-durable-profile-isolation-and-proactive-continuity-carry-through-hardening/24-IMPLEMENTATION-CONTRACT.md)
- doctrine:
  - correctness first
  - shared-seam diagnosis before patching
  - no SHIBA-style uplift by default
  - no reopening of the settled Phase `22` boundary without direct evidence
- explicit repair order:
  - principal-scoped durable profile isolation
  - then proactive continuity carry-through hardening
- recommended next step:
  - `/gsd-execute-phase 24`

## Phase 24 Closeout

- `24` is execution-complete.
- summary:
  - [24-01-SUMMARY.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/24-principal-scoped-durable-profile-isolation-and-proactive-continuity-carry-through-hardening/24-01-SUMMARY.md)
- deepest new truths:
  - the `cross_principal_profile_bleed` bug was a durable storage / scoped lookup seam, not just a missing metadata tag
  - the `proactive_continuity_after_reset` miss was a continuation salience / synthesis-guidance seam, not a simple “memory forgot it” loss
  - the two residuals were causally separate, so a fake shared fix would have been the wrong move
- primary artifacts:
  - [phase24-principal-bleed-canary.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase24/phase24-principal-bleed-canary.json)
  - [phase24-carry-through-deterministic.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase24/phase24-carry-through-deterministic.json)
  - [phase24-live-proactive-rerun.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase24/phase24-live-proactive-rerun.json)
- validation truth:
  - Brainstack source targeted slice: `15 passed`
  - Bestie mirror targeted slice: `62 passed`
  - own-scope `ruff` / `mypy`: clean in both repos
- reading:
  - the two post-Phase-23 residuals should now be treated as closed at their proven seams
  - the correct next move is not another immediate correction phase
  - it is:
    - checkpoint Phase `24`
    - then optionally refresh the broader deployed-live baseline on top of the new truth

## Phase 24 Checkpoint

- the `24` result is now the current correctness baseline for the Phase `23` residuals
- this checkpoint freezes the current reading:
  - the principal-scoped durable profile bleed should be treated as closed at the durable storage / scoped lookup seam
  - the proactive continuity carry-through miss should be treated as closed at the continuation-salience / synthesis-guidance seam
  - the settled Phase `22` Brainstack/native boundary still stands
- the focused proof set is now part of the settled baseline:
  - [phase24-principal-bleed-canary.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase24/phase24-principal-bleed-canary.json)
  - [phase24-carry-through-deterministic.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase24/phase24-carry-through-deterministic.json)
  - [phase24-live-proactive-rerun.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase24/phase24-live-proactive-rerun.json)
- the next recommended work should consume Phase `24` as settled truth instead of reopening the same corrective seams by default

## Phase 25 Planning Closeout

- `25` has been added and planned.
- goal:
  - refresh the broader deployed-live quality baseline on top of the settled Phase `24` truth
- planned files:
  - [25-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/25-broader-deployed-live-quality-baseline-refresh/25-CONTEXT.md)
  - [25-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/25-broader-deployed-live-quality-baseline-refresh/25-01-PLAN.md)
  - [25-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/25-broader-deployed-live-quality-baseline-refresh/25-IMPLEMENTATION-CONTRACT.md)
- doctrine:
  - validation first
  - no stealth corrective phase by default
  - no reopening of the settled Phase `22` boundary without direct evidence
  - no reopening of the settled Phase `24` seam fixes without direct evidence
  - honest comparison against the older Phase `23` baseline
- recommended next step:
  - `/gsd-execute-phase 25`

## Phase 25 Closeout

- `25` is execution-complete as a baseline-refresh validation phase.
- summary:
  - [25-01-SUMMARY.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/25-broader-deployed-live-quality-baseline-refresh/25-01-SUMMARY.md)
- broader live truth:
  - the top-line result stayed `9 / 10`
  - but the residual map improved relative to Phase `23`
  - `cross_principal_profile_bleed` no longer appeared in the broader live read
  - `larger_knowledge_body` improved from `acceptable_pass` to `strong_pass`
- remaining residual:
  - `proactive_continuity_after_reset`
  - focused variance check:
    - [brainstack-25-proactive-variance-check.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase25/brainstack-25-proactive-variance-check.json)
    - `2 / 3` pass
    - `intermittent = true`
- reading:
  - this does **not** justify reopening the settled Phase `22` boundary
  - this does **not** justify reopening the Phase `24` profile-isolation seam
  - the remaining weakness reads as narrower live proactive carry-through variance, not a broad correctness regression
- recommended next step:
  - checkpoint Phase `25`
  - then only consider a focused proactive continuity robustness follow-up if the project wants to chase the final residual instead of accepting the current baseline

## Phase 25 Checkpoint

- the `25` result is now the current broader deployed-live quality baseline on top of the settled Phase `24` truth
- this checkpoint freezes the current reading:
  - the top-line broader live result remains `9 / 10`
  - `cross_principal_profile_bleed` should stay treated as closed in the broader live baseline
  - `larger_knowledge_body` should stay treated as improved from `acceptable_pass` to `strong_pass`
  - the only carried residual is narrower live proactive continuity variance
- the settled interpretation after this checkpoint is:
  - this does **not** justify reopening the settled Phase `22` Brainstack/native boundary
  - this does **not** justify reopening the Phase `24` profile-isolation seam
  - any further work should treat the remaining `proactive_continuity_after_reset` weakness as a focused robustness thread, not as a broad correctness regression
- the focused proof set is now part of the settled baseline:
  - [brainstack-25-broader-deployed-live-eval.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase25/brainstack-25-broader-deployed-live-eval.json)
  - [brainstack-25-scenario-matrix.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase25/brainstack-25-scenario-matrix.json)
  - [brainstack-25-proactive-variance-check.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase25/brainstack-25-proactive-variance-check.json)
- the next recommended work should consume Phase `25` as settled truth instead of rerunning the same baseline by default

## Phase 26 Planning Closeout

- `26` has been added and planned.
- goal:
  - close the remaining proactive continuity residual under stricter gates
- planned files:
  - [26-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/26-focused-proactive-continuity-robustness/26-CONTEXT.md)
  - [26-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/26-focused-proactive-continuity-robustness/26-01-PLAN.md)
  - [26-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/26-focused-proactive-continuity-robustness/26-IMPLEMENTATION-CONTRACT.md)
- doctrine:
  - focused robustness first
  - no broad capability expansion
  - no reopening of the settled Phase `22`, `24`, or `25` readings without direct evidence
  - stricter pass/fail gates, not looser wording
- the strict filters are explicit:
  - event-frame restoration
  - no-detour proactive continuation
  - selective recall / low token waste
  - whole-path diagnosis, not memory-kernel-only blame
- recommended next step:
  - `/gsd-execute-phase 26`

## Deferred Tech Debt Note

- the remaining proactive continuity `1 / 10` residual should now be treated as
  deferred technical debt, not as an active immediate fix thread
- the deferred reading is:
  - do **not** reopen it via more host-prompt or heuristic micro-fixes
  - keep it parked as a separate much-later technical debt item until there is
    a genuinely better reason to revisit it
- backlog parking item:
  - [999.1-deferred-proactive-continuity-residual](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/999.1-deferred-proactive-continuity-residual)

## Phase 27 Planning Closeout

- a new active phase is now planned for selective `hermes-lcm` host-level donor uptake:
  - [27-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/27-selective-hermes-lcm-host-level-donor-uptake/27-CONTEXT.md)
  - [27-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/27-selective-hermes-lcm-host-level-donor-uptake/27-01-PLAN.md)
  - [27-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/27-selective-hermes-lcm-host-level-donor-uptake/27-IMPLEMENTATION-CONTRACT.md)
- the donor audit reading behind this phase is:
  - full `LCM` integration is not the right move now
  - selective donor uptake is the right move only for the small host-level slices with strong ROI
- the ordered candidate set is:
  - source-window / compaction provenance
  - explicit lifecycle / frontier state
  - bounded expand/search ergonomics over compacted history
  - conditional ignored/stateless-session filtering
- the implementation doctrine is explicit:
  - donor-first, not donor-transplant
  - utility-first, not donor adoption for its own sake
  - no second compaction runtime
  - no second durable truth owner
  - no broad host rewrite
  - no token-heavy UX regression
  - Brainstack-first implementation, Bestie-later validation/mirroring
- execute must begin with a duplicate/overlap audit:
  - if a candidate seam already exists partially in Brainstack, extend it instead of recreating it
- any donor slice should be stopped if it creates more maintenance pain than real product value
- the session-filtering slice remains conditional:
  - ship it only if noisy/stateless-session evidence is real
  - otherwise defer it inside the phase rather than padding scope

## Phase 20.19 Closeout

- `20.19` is execution-complete at gate, but not as a clean full live pass.
- summary:
  - [20.19-01-SUMMARY.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.19-live-graph-corpus-backend-enablement-and-post-enablement-isolated-rebaseline/20.19-01-SUMMARY.md)
- planning files:
  - [20.19-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.19-live-graph-corpus-backend-enablement-and-post-enablement-isolated-rebaseline/20.19-CONTEXT.md)
  - [20.19-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.19-live-graph-corpus-backend-enablement-and-post-enablement-isolated-rebaseline/20.19-01-PLAN.md)
  - [20.19-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.19-live-graph-corpus-backend-enablement-and-post-enablement-isolated-rebaseline/20.19-IMPLEMENTATION-CONTRACT.md)
- real win:
  - Bestie checkout `.venv` now imports `kuzu` and `chromadb`
  - activation proof shows live Brainstack can instantiate `KuzuGraphBackend` and `ChromaCorpusBackend`
- explicit artifacts:
  - activation proof: `reports/phase20/brainstack-20.19-activation-proof.json`
  - doctor read: `reports/phase20/brainstack-20.19-doctor.txt`
  - post-enablement isolated live baseline: `reports/phase20/brainstack-bestie-live-reset-eval-isolated.json`
  - harness-faithful live debug: `reports/phase20/brainstack-20.19-live-debug.json`
- enabled-stack truth:
  - `semantic` is no longer degraded in the isolated live path
  - `graph` is no longer degraded in the isolated live path
  - `aggregate_total` now passes in the post-enablement isolated live baseline
- but the closeout is not fake-green:
  - the full isolated live baseline remained `3 / 5`
  - the enabled-stack packet is still usually transcript/continuity-dominant
  - the debug slice shows active channels, but `graph_rows` / `corpus_rows` still do not win the final selected block consistently
  - the checkout-level doctor still reports config truth gaps (`memory.provider`, builtin memory flags, missing `plugins.brainstack` section)
- honest reading:
  - the main blocker is no longer “graph/corpus unavailable”
  - the next blocker is enabled-stack bridge + stability:
    - graph/corpus evidence becoming decisive in the final packet
    - native aggregate surfacing on the live path
    - stable enabled-stack live correctness across reruns

## Phase 20.16 Closeout

- `20.16` execute completed at gate as a triage phase, not an aggregate-expansion phase.
- corrected isolated reset eval:
  - `reports/phase20/brainstack-bestie-live-reset-eval-isolated.json`
  - result: `3 / 5`
- localized packet audit:
  - `reports/phase20/brainstack-20.16-isolated-live-packet-localization.json`
- strongest new findings:
  - the remaining live failures are not simple no-write admission misses; the failing facts are persisted into transcript/continuity shelves
  - the current live recall path can still surface transcript rows from unrelated isolated users/sessions, so principal-scoped retrieval isolation is now a first-class blocker
  - noun-`order` queries can still misroute into temporal mode (`coffee_order`), so route disambiguation is also now a first-class blocker
  - the reset/live path still ended with `profile_items = 0`, so preference/routine-style recall is relying on continuity/transcript competition rather than strong durable profile surfacing
  - the localized live packet audit also showed `semantic` and `graph` channels degraded in the deployed Bestie runtime, so immediate `20.17` live gains should be expected on the active `keyword + temporal` stack; graph/corpus-backed live enablement remains separate
- because of that `20.16` closeout, the next thread should **not** be blind broader aggregate expansion
- the next phase should instead target:
  - principal-scoped live recall isolation
  - generic `order` route disambiguation
  - bounded reset-boundary bridge hardening on deployed Bestie

## Phase 20.17 Closeout

- `20.17` executed the bounded live isolation / route disambiguation pass, plus one reset-boundary principal carry-through hardening fix in the gateway finalize path
- summary:
  - [20.17-01-SUMMARY.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.17-principal-scoped-live-recall-isolation-and-route-disambiguation/20.17-01-SUMMARY.md)
- strongest new truths:
  - cross-principal leakage is no longer the dominant live packet failure
  - bare noun `order` no longer drives `coffee_order` into temporal routing
  - reset-boundary `session_summary` rows now preserve principal scope
  - deployed Bestie still runs with `semantic` / `graph` degraded, so current live gains are on the active `keyword + temporal` stack
  - the remaining structural live blocker is now narrower:
    - same-principal low-overlap temporal ordering recall can still under-surface a full event chain (`temporal_order`)
  - the remaining `coffee_order` / `gift_context` misses now read more like packet-use / synthesis weakness than principal leakage
- current live artifacts:
  - isolated live eval:
    - [brainstack-bestie-live-reset-eval-isolated.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase20/brainstack-bestie-live-reset-eval-isolated.json)
    - latest repeated result: `2 / 5`
  - packet localization:
    - [brainstack-20.17-isolated-live-packet-localization.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase20/brainstack-20.17-isolated-live-packet-localization.json)

## Phase 20.18 Closeout

- `20.18` executed the bounded low-overlap live surfacing pass on top of the `20.17` principal/route fixes
- summary:
  - [20.18-01-SUMMARY.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/20.18-low-overlap-live-surfacing-and-packet-sufficiency-vs-synthesis-split/20.18-01-SUMMARY.md)
- strongest new truths:
  - bounded same-principal support carry-through is now real in source and mirrored into Bestie runtime
  - `coffee_order` and `gift_context` now pass on the degraded live stack
  - `temporal_order` still fails on deployed Bestie as the remaining low-overlap same-principal ordering miss
  - `aggregate_total` still fails because the earlier graph/native aggregate capability is still not active in the deployed live runtime
  - the live ceiling is therefore now more honestly explained by missing runtime enablement than by one more round of degraded keyword-only tuning
- current live artifact:
  - isolated live eval:
    - [brainstack-bestie-live-reset-eval-isolated.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase20/brainstack-bestie-live-reset-eval-isolated.json)
    - result: `3 / 5`

## Phase 27 Closeout

- `27` closed as a selective `hermes-lcm` donor-uptake phase, not as donor integration.
- overlap/utility reading:
  - `source-window / compaction provenance` was already partial in Brainstack and was extended on the existing continuity snapshot seam
  - `lifecycle / frontier state` was the clean missing seam and landed as a thin Brainstack-owned substrate
  - `bounded expand/search ergonomics` was explicitly deferred because partial overlap already exists and the donor runtime coupling was not clean enough for this phase
  - `ignored/stateless-session filtering` was explicitly deferred because noisy-session evidence was not strong enough
- landed Brainstack source changes:
  - richer bounded snapshot provenance under `metadata.provenance`
  - explicit `continuity_lifecycle_state` tracking for compaction/frontier/finalization checkpoints
  - provider hook updates only at:
    - `on_pre_compress`
    - `on_session_end`
- validation:
  - targeted slice: `14 passed`
  - broader affected slice: `17 passed`
  - `ruff` clean
  - `mypy --follow-imports=silent --ignore-missing-imports` clean
- important boundary truth:
  - no new host plugin slot
  - no second compaction runtime
  - no second truth owner
  - no Bestie-side duplicate implementation in this phase

## Phase 27 Checkpoint

- `27` is now the settled donor-uptake baseline.
- the accepted landed scope is frozen as:
  - bounded snapshot provenance on the existing continuity snapshot seam
  - thin Brainstack-owned lifecycle/frontier state
- the accepted deferred scope is frozen as:
  - bounded expand/search ergonomics
  - ignored/stateless-session filtering
- the checkpoint reading is explicit:
  - this phase improved Brainstack host seams
  - it did not justify `LCM` runtime integration
  - it did not justify a new host plugin slot
  - it did not justify Bestie-side parallel implementation

## Phase 27.1 Closeout

- `27.1` mirrored the landed Phase `27` slices into Bestie without local redesign.
- mirrored scope:
  - bounded snapshot provenance
  - thin lifecycle/frontier state
- measured truth:
  - auditability / diagnostics improved materially
  - ordinary-turn token surface stayed neutral in the measured scenario
  - retrieval usefulness uplift was not proven
- validation:
  - targeted Bestie slice: `52 passed`
  - `ruff` clean
  - `mypy --follow-imports=silent --ignore-missing-imports` clean
- important reading:
  - this phase proves correct Bestie mirroring and a narrow diagnostics win
  - it does not prove a broader retrieval/product-quality lift beyond that

## Phase 27.1 Checkpoint

- `27.1` is now the settled Bestie mirror baseline for the landed Phase `27` donor slices.
- accepted mirrored scope:
  - bounded snapshot provenance
  - thin lifecycle/frontier state
- settled measured reading:
  - auditability / diagnostics improved
  - ordinary-turn token surface stayed neutral in the measured scenario
  - retrieval usefulness uplift remains unproven
- boundary reading:
  - this checkpoint confirms correct Bestie mirroring and a narrow operational win
  - it does not justify broader retrieval/product-quality claims

## Phase 28 Planning Closeout

- a new active phase is now planned for targeted upstream donor delta audit and selective refresh:
  - [28-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/28-targeted-upstream-donor-delta-audit-and-selective-refresh/28-CONTEXT.md)
  - [28-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/28-targeted-upstream-donor-delta-audit-and-selective-refresh/28-01-PLAN.md)
  - [28-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/28-targeted-upstream-donor-delta-audit-and-selective-refresh/28-IMPLEMENTATION-CONTRACT.md)
- this phase is explicitly worth doing, but only as a bounded selective audit:
  - the expected ROI is medium
  - the acceptable final result may still be audit-only no-op
- the planning reading is:
  - Hindsight is the strongest immediate donor candidate
  - MemPalace is likely audit-only unless boundary leakage is found
  - Graphiti should remain explicit no-op unless the audit finds a concrete runtime-ROI delta
- the doctrine is explicit:
  - no blanket donor sync
  - no donor vanity adoption
  - no Bestie-side implementation in this phase
  - no broad rewrite or new runtime dependency
  - no code change if the current local seam already covers the donor value
- execute must begin with an explicit donor-delta matrix and a shipped-vs-no-op-vs-defer verdict for each donor

## Phase 29 Execute Complete At Gate

- the correctness-first phase for the communication-contract regression is now planned and locally executed:
  - [29-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29-live-communication-contract-recall-and-post-reset-durability-forensics/29-CONTEXT.md)
  - [29-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29-live-communication-contract-recall-and-post-reset-durability-forensics/29-01-PLAN.md)
  - [29-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29-live-communication-contract-recall-and-post-reset-durability-forensics/29-IMPLEMENTATION-CONTRACT.md)
- final seam verdict:
  - primary seam:
    - legacy unscoped principal-scoped communication preferences were being dropped at the scoped retrieval / active-contract boundary
  - secondary correctness bug:
    - Tier-2 worker and session-end flush could fail before promotion because the Tier-2 caller used an unsupported `response_format` keyword
- ruled out:
  - total absence of durable communication data
  - prompt weakness as the real cause
  - pure application-only override after a correct contract was already present
- final bounded repair:
  - deterministic open-time backfill for legacy unscoped principal-scoped profile rows
  - Tier-2 caller fix through `extra_body`
- deployed-path proof after repair:
  - live scoped keys now exist in the docker runtime
  - a fresh deployed-path `AIAgent._build_system_prompt()` rebuilds the full communication contract for the affected principal
  - isolated runtime provider proof shows `on_session_end()` can again land scoped preference truth
- residual note:
  - principal-model drift between old and new principal naming shapes remains adjacent work, but it was not required to close the Phase `29` regression

## Phase 29.1 Execute Complete At Gate

- the durable-shape hardening follow-up is now locally executed and deployed-path validated:
  - [29.1-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.1-canonical-communication-contract-and-durable-identity-captur/29.1-CONTEXT.md)
  - [29.1-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.1-canonical-communication-contract-and-durable-identity-captur/29.1-01-PLAN.md)
  - [29.1-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.1-canonical-communication-contract-and-durable-identity-captur/29.1-IMPLEMENTATION-CONTRACT.md)
  - [29.1-01-SUMMARY.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.1-canonical-communication-contract-and-durable-identity-captur/29.1-01-SUMMARY.md)
- final seam verdict:
  - communication durability was a bounded contract-shape / compatibility problem, not mainly a retrieval failure
  - explicit age durability was a capture-gap problem in the active Tier-2 path, not mainly a prompt weakness
- final bounded repair:
  - shared contract helper for slot normalization and communication shaping
  - deterministic Tier-2 explicit-age fallback for explicit self-statements only
  - versioned one-shot compatibility migrations:
    - `canonical_communication_rows_v1`
    - `explicit_identity_backfill_v1`
- deployed-path proof after repair:
  - rebuilt `hermes-final` image and force-recreated the running `hermes-bestie` container
  - verified the running container contains the explicit-age migration code
  - verified the live DB now contains:
    - `canonical_communication_rows_v1`
    - `explicit_identity_backfill_v1`
    - `identity:age => 19 years old`
  - verified the active prompt block still reconstructs the communication contract cleanly and now includes the age fact in the profile block
- ruled out:
  - runtime style-policing as the right fix
  - broad Tier-1 handwritten inference rollback
  - donor-side direct transplant from Graphiti for a profile-owner seam

## Phase 29.2 Execute Complete At Gate

- the practical logistics boundary phase is now locally executed and deployed-path validated:
  - [29.2-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.2-practical-logistics-memory-capture-and-reminder-boundary-aud/29.2-CONTEXT.md)
  - [29.2-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.2-practical-logistics-memory-capture-and-reminder-boundary-aud/29.2-01-PLAN.md)
  - [29.2-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.2-practical-logistics-memory-capture-and-reminder-boundary-aud/29.2-IMPLEMENTATION-CONTRACT.md)
  - [29.2-01-SUMMARY.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.2-practical-logistics-memory-capture-and-reminder-boundary-aud/29.2-01-SUMMARY.md)
- final seam verdict:
  - stable logistics provider/place facts were surviving only through transcript/continuity and needed durable capture
  - Chron already owned the real reminder execution state and should not be duplicated
  - same-day transient todos did not justify durable promotion
- final bounded repair:
  - added a narrow logistics helper for explicit provider/place declarations only
  - reused the existing typed-entity / graph shelf instead of adding a new logistics shelf
  - added versioned compatibility repair:
    - `stable_logistics_typed_entities_v2`
- deployed-path proof after repair:
  - rebuilt the `hermes-final` runtime image and force-recreated the live `hermes-bestie` container
  - verified the running container contains the logistics helper, the `v2` migration, and the user-segment transcript cleanup
  - triggered a real prompt build in the running container so Brainstack opened the live store
  - verified the live DB now contains:
    - `stable_logistics_typed_entities_v1`
    - `stable_logistics_typed_entities_v2`
    - current graph truth for `Móni`
    - clean current `address = Kassák Lajos 87 44es kapucsengő 4em`
    - current `category = talpmasszázs`
  - verified the earlier malformed prefixed address remains only as historical state
  - verified `Fodrász / Bank` still do not appear in durable profile or current graph truth
  - verified native Chron still owns the real reminder jobs in `cron/jobs.json`
- ruled out:
  - promoting all logistics text into profile rows
  - building a reminder shadow database inside Brainstack
  - promoting same-day todos into durable memory by default
  - solving stable logistics recall through transcript luck alone

## Combined 29.1 + 29.2 Verify Verdict

- combined deployed-path verify was run against the live `hermes-final` / `hermes-bestie` runtime
- verification artifact:
  - [29.2-UAT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.2-practical-logistics-memory-capture-and-reminder-boundary-aud/29.2-UAT.md)
- final score:
  - 5 / 6 checks passed
  - 1 diagnosed minor gap remains
- confirmed passes:
  - durable principal-scoped `identity:age` row exists
  - deployed prompt still contains the core communication contract
  - durable provider/place graph truth works for `Móni`
  - transient same-day todos still do not pollute durable shelves
  - native Chron still owns reminder jobs
- diagnosed residual:
  - direct age recall is not yet preferring the durable identity row strongly enough on the deployed prefetch path
  - the system can still answer correctly, but it is still leaning on continuity/transcript evidence for that direct query

## Phase 29.3 Closed

- final artifacts:
  - [29.3-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.3-full-humanizer-contract-durability-and-style-pack-forensics/29.3-CONTEXT.md)
  - [29.3-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.3-full-humanizer-contract-durability-and-style-pack-forensics/29.3-01-PLAN.md)
  - [29.3-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.3-full-humanizer-contract-durability-and-style-pack-forensics/29.3-IMPLEMENTATION-CONTRACT.md)
  - [29.3-01-SUMMARY.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.3-full-humanizer-contract-durability-and-style-pack-forensics/29.3-01-SUMMARY.md)
  - [29.3-UAT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.3-full-humanizer-contract-durability-and-style-pack-forensics/29.3-UAT.md)
- final verdict:
  - compact communication slots remain the operational lane
  - one canonical principal-scoped `preference:style_contract` row now owns detailed Humanizer recall
  - explicit style/rules questions use the existing model-backed route seam
  - ordinary turns explicitly exclude the long-form style contract
  - legacy corpus-backed style artifacts are migrated into the canonical profile lane and retired
  - install-time hardening now routes `flush_memories` through the main provider for more reliable Tier-2 writes
- live proof:
  - `hermes-bestie` container healthy
  - active canonical `preference:style_contract` row exists in the live DB
  - legacy corpus style-contract document is inactive
  - explicit `Tudod a 29 szabályt?` runtime prefetch resolves to `style_contract`
  - ordinary `Beszélgessünk egy kicsit!` runtime prefetch does not include the long-form style contract

## Phase 29.4 Closed

- final artifacts:
  - [29.4-CONTEXT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.4-oracle-regression-runner-repair-and-pre-forensics-gate/29.4-CONTEXT.md)
  - [29.4-01-PLAN.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.4-oracle-regression-runner-repair-and-pre-forensics-gate/29.4-01-PLAN.md)
  - [29.4-IMPLEMENTATION-CONTRACT.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.4-oracle-regression-runner-repair-and-pre-forensics-gate/29.4-IMPLEMENTATION-CONTRACT.md)
  - [29.4-01-SUMMARY.md](/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/phases/29.4-oracle-regression-runner-repair-and-pre-forensics-gate/29.4-01-SUMMARY.md)
- final verdict:
  - the old oracle retrieval-only runner had become an untrustworthy gate because it still depended on benchmark-only remote wiring and incomplete runtime parity
  - after bounded repair, the `oracle 60` retrieval-only rerun no longer shows broad retrieval-health collapse
  - therefore recent `29.x` product work is not currently falsified by the oracle gate
- bounded proof:
  - oracle rerun completed `60 / 60`
  - `memory_context_present`: `60 / 60`
  - `backend_population_nonzero`: `60 / 60`
  - `zero_backend_cases`: `0`
  - `empty_text_batches`: `0`
  - route pairs:
    - `fact/fact`: `25`
    - `aggregate/aggregate`: `20`
    - `temporal/temporal`: `15`
- comparison to prior recorded oracle baseline:
  - earlier `70`-item spillover had `22` zero-backend cases and `19` empty-text batches
  - the repaired bounded gate has neither of those failure classes
- handoff:
  - the next exact seam is not runner health
  - the next exact seam is live detailed style-contract ingest fidelity
  - the active canonical `preference:style_contract` row is being served, but it currently stores a shortened ruleset instead of the full taught contract

## Phase 29.7 Verify Learning

- `29.7` proved an additional runtime-parity invariant that must stay explicit in future behavior-policy verify work:
  - active docker runtime checks must use the actual gateway interpreter, not a bare container `python3` probe
- concrete live finding:
  - inside `hermes-bestie`, bare `python3` did not expose `kuzu`, `chromadb`, or `openai`
  - the actual gateway process runs `/opt/hermes/.venv/bin/python3 /opt/hermes/.venv/bin/hermes gateway run --replace`
  - the gateway interpreter did expose all three packages and correctly executed the `29.7` immediate-activation smoke
- implication:
  - future parity and doctor work must distinguish:
    - container presence
    - gateway health
    - gateway interpreter dependency surface
  - otherwise runtime checks can report false red while the deployed behavior path is actually green

## Phase 29.9 Execute Learning

- `29.9` answer-level harness design surfaced another verify invariant for behavior-policy work:
  - future obedience verify must distinguish prompt-surface presence from model obedience
- concrete evidence:
  - the Brainstack provider contributes behavior policy through two ordinary-turn surfaces:
    - `system_prompt_block()` via the external memory provider system prompt seam
    - `prefetch_all()` via user-message injection
  - therefore a live miss can mean:
    - the compiled policy never reached prompt assembly
    - the policy reached prompt assembly but the final answer still did not obey it
    - or the harness/runtime seam failed before either could be measured
- implication:
  - future `29.9+` verify work must report those classes separately
  - otherwise the project will keep misdiagnosing live behavior failures as storage/retrieval bugs

## Phase 29.9 Verify Findings

- the new answer-level obedience harness is live and rerunnable against the deployed `hermes-final` / `bestie` path
- live result:
  - `2 / 3` scenarios passed
  - `1 / 3` startup smalltalk scenario failed on final-answer obedience
  - one same-session scenario produced a mechanically acceptable answer while the compiled behavior policy was still inactive
- exact diagnosed residuals:
  - `startup_smalltalk_after_reset`
    - compiled behavior policy was active
    - system authority was present in both cached system prompt and provider system block
    - final answer still violated the expected behavior contract by falling back to a generic greeting/follow-up shape
  - `ordinary_help_same_session`
    - the answer passed the bounded mechanical checker
    - but compiled behavior policy remained inactive in the persisted scope snapshot
    - this means the same-session plain-conversation teaching path is still not a trustworthy activation owner
- implication:
  - current remaining gap is not "Brainstack cannot store the policy" anymore
- the remaining gaps are:
    - prompt-present but not obeyed startup behavior
    - same-session activation truth still weaker than the reset/deployed path

## Phase 29.10 Execute Learning

- the minimal high-value `29.10` slice is:
  - raw-vs-compiled behavior-policy snapshot
  - provider-level per-surface trace
  - explicit deterministic rule correction
  - doctor/runtime parity proof
- important implementation boundary:
  - this did not require a new owner system or new policy pipeline
  - the right seam was to extend the existing canonical `style_contract` + compiled policy path with inspectable surfaces
- concrete runtime lesson:
  - the provider trace must distinguish at least:
    - `system_prompt_block`
    - `prefetch`
  - otherwise live misses keep collapsing into a single opaque “policy was active” claim
- concrete parity lesson:
  - docker dependency checks must probe the actual gateway interpreter path first
  - for the current `bestie` runtime this means preferring `/opt/hermes/.venv/bin/python3`
  - otherwise doctor can report false-red dependency failures even when the deployed gateway path is green
- residual anomaly:
  - direct CLI execution of `scripts/brainstack_doctor.py` can still report false-red dependency failures
  - the same module invoked via `run_doctor()` / `main()` in-process returned the correct green result
  - treat this as a doctor CLI seam bug to close during `verify 29.10`, not as a backend dependency regression

## Phase 29.10 Verify Findings

- source surface:
  - `ruff` passed on the modified files
  - `tests/test_brainstack_phase29_style_contract.py` passed with the new snapshot / trace / correction coverage
  - `tests/test_brainstack_real_world_flows.py` remained green
- final surface:
  - `hermes-final` was reinstalled from source-of-truth successfully
  - host-side `hermes-final` interpreter proved:
    - prompt title injection
    - prefetch projection presence
    - active compiled-policy snapshot
    - per-surface trace population
    - explicit rule correction with parity preserved
- runtime/doctored parity:
  - the doctor module returned fully green results when invoked through `run_doctor()` / `main()` and when forced through a `runpy` `__main__` path
  - the same CLI path executed through a Python subprocess also returned fully green results
  - docker/runtime parity therefore appears correct at the logic level
- residual classification update:
  - the earlier false-red seen from a direct shell invocation under the Codex exec surface did not reproduce when the same CLI was invoked through Python subprocess
  - treat that discrepancy as an external execution-surface anomaly, not a Brainstack doctor/runtime parity bug

## Phase 30.0 Execute Learning

- the minimal donor-first `30.0` slice must stay a derived operating-context projection, not a new durable owner
- the right inputs are existing truth classes only:
  - compiled behavior policy for ordinary-turn behavior authority presence
  - stable profile items for identity/shared-work anchors
  - continuity `tier2_summary` rows for current work
  - continuity `decision` rows for open decisions
  - continuity lifecycle state for transient same-session activity
- important boundary:
  - the operating-context section must not duplicate or replace the compiled behavior contract
  - communication behavior remains owned by the compiled behavior policy only
- proactive rule shape:
  - allow only a conservative resume-active-work hint when the session is active and concrete work/decision context exists
  - do not infer or own reminders, scheduling, or task truth
- prompt-shape consequence:
  - `system_prompt_block()` may now carry a bounded `# Brainstack Operating Context` section
  - that section is informational and continuity-oriented, not a second behavior-policy plane

## Phase 30.0 Verify Findings

- source surface:
  - `ruff` passed on the new operating-context module and touched seams
  - `tests/test_brainstack_phase30_operating_context.py` passed
  - `tests/test_brainstack_phase29_style_contract.py` stayed green, so the operating-context slice did not regress the existing behavior-policy lane
- final surface:
  - `hermes-final` was reinstalled from source-of-truth
  - the direct shell doctor CLI again showed false-red dependency/plugin noise and should not be treated as the authoritative parity signal
  - authoritative in-process doctor invocation returned green with no failed checks
  - the `hermes-final` interpreter proved:
    - `# Brainstack Operating Context` is present in `system_prompt_block()`
    - active work and open decisions surface into the section
    - owner-boundary wording stays explicit
    - provider snapshot and trace surfaces both populate correctly
- live runtime surface:
  - `hermes-bestie` was rebuilt and returned healthy
  - the real gateway interpreter inside the container proved the same operating-context snapshot / trace behavior as the host `final` interpreter
  - the bounded projection survived the deployed runtime path without creating a new durable owner or taking over reminders / scheduling
- important closure:
  - `30.0` is now proven as an always-on operating-context projection layer, not a shadow task or scheduler system

## Phase 30.1 Execute Learning

- the first `30.1` slice should prove separation with an offline-only pilot, not with live graph integration
- the right bounded shape is:
  - explicit source document identity
  - deterministic sections and chunks with offsets
  - explicit claim candidates
  - evidence-span binding against document text
  - conflict candidates for disagreeing evidence-backed claims
- important fail-closed rule:
  - missing evidence snippets must fail the offline pilot build instead of creating unsupported claims
- important boundary:
  - the pilot does not write to live Brainstack graph, corpus, profile, or continuity stores
  - this keeps the offline document path separate from the chat-time memory kernel while still proving the target KG/evidence shape

## Phase 30.1 Verify Findings

- source surface:
  - `uvx ruff check brainstack/knowledge_schema.py brainstack/document_pipeline.py tests/test_brainstack_phase30_1_document_pipeline.py` passed
  - `tests/test_brainstack_phase30_1_document_pipeline.py` passed
  - `tests/test_brainstack_phase30_operating_context.py` stayed green, so the offline pilot did not regress the `30.0` operating-context slice
- final surface:
  - `hermes-final` was reinstalled from source-of-truth
  - the authoritative doctor CLI returned green with no failed checks
  - the installed payload contains both `document_pipeline.py` and `knowledge_schema.py`
  - the `hermes-final` interpreter proved the offline pilot can be imported and executed there
  - the `hermes-final` smoke also proved the boundary:
    - `offline_only = true`
    - documents / sections / chunks / claims / evidence spans are produced
    - profile / graph / corpus store counts remain zero
- architecture closure:
  - `30.1` is now proven as an offline document-to-claim / evidence pilot only
  - there is still no live provider / retrieval / graph integration path for this module, which is the correct donor-first boundary for this phase

## Phase 30.2 Investigation Findings

- the live task failure is not a pure write failure:
  - the live DB already contains a `tier2_summary` for the user's three tasks
  - therefore “Brainstack did not save it” is not the precise diagnosis
- the live task failure is a retrieval / contract mismatch:
  - `recent_continuity()` is session-scoped
  - cross-session continuity search is lexical
  - the new task summary was stored in English
  - Hungarian task queries therefore missed it in the observed live run
- the live task boundary is currently explicit in code:
  - Brainstack says reminders, scheduling, and task truth stay with native owners
  - so the assistant's promise of durable task ownership is not aligned with the current architecture
- the live rule-obedience residual is not only “model drift”:
  - the canonical scoped `style_contract` row itself can still be `tier2_llm`-derived
  - that row is already lossy / mutated in stored raw content
- the same-session correction residual is not yet formalized:
  - ordinary chat correction is not automatically the same path as explicit behavior-policy correction
  - this leaves a gap between what the assistant claims and what the system actually upgrades in-session
- phase-split decision:
  - `30.2` should close product-truth residuals in the memory layer itself:
    - style-contract source fidelity
    - projection / no-silent-drop semantics
    - plain-chat pre-answer activation
    - same-session correction semantics
    - Hungarian continuity retrieval contract
  - `30.3` should close host/runtime compliance gaps:
    - hard surface validators
    - truthful write receipts
    - reset barriers
    - truthful null-result semantics
    - tool-routing correctness
  - `30.4` should resolve the task / commitment truth-class question explicitly rather than smuggling it into `30.2`

## Phase 30.2 Execute Learning

- plain-chat structured rule packs now activate pre-answer in `prefetch()`, not only post-answer in `sync_turn()`
- style-contract precedence is now explicit:
  - deterministic scoped writes outrank weaker `tier2_llm` style-contract writes
  - this closes the path where a lossy Tier-2 canonical row could silently retake authority after a stronger deterministic write
- behavior-policy truth is now split more honestly:
  - compile coverage remains visible
  - ordinary projection completeness is separate
  - bounded omission moves the ordinary-turn policy into `degraded` status instead of silently green “active”
- ordinary user correction is now explicit in `30.2`:
  - not a durable policy rewrite by default
  - but a bounded session-local reinforcement path exists for immediate replies when the user clearly calls out an active policy drift
- the task residual stays within donor-first boundaries in `30.2`:
  - Brainstack still does not silently become the durable task owner
  - Hungarian reset-time task recall is improved through bounded bilingual continuity query expansion

## Phase 30.2 Verify Findings

- source surface:
  - the targeted `30.2` regression suite stayed green
  - the relevant phase `29` and retrieval / operating-context guard suites also stayed green
- shim surface:
  - the shim worktree plugin payload was stale before verify
  - it was resynced directly from the source Brainstack plugin payload
  - file-hash parity now matches for the changed `30.2` files
  - a direct shim-interpreter smoke confirmed pre-answer structured plain-chat activation still works there
- `hermes-final` surface:
  - the Brainstack payload was reinstalled into `hermes-final`
  - direct interpreter smoke proved:
    - structured plain-chat contracts activate before the first post-teach answer
    - deterministic style-contract rows are not silently overwritten by weaker `tier2_llm` writes
    - projection truth is reported as `degraded` when bounded omission occurs
    - same-session correction creates bounded reinforcement instead of a silent durable rewrite
    - Hungarian task queries can recover English continuity summaries across sessions
- live runtime surface:
  - `hermes-bestie` was rebuilt and returned healthy
  - direct container interpreter smoke proved the same `30.2` invariants on the rebuilt runtime
  - direct container import probes confirmed `kuzu`, `chromadb`, and `openai` are present in the active runtime
- named non-blocker residual:
  - the shell/CLI `brainstack_doctor.py --json` path still reports false-red docker dependency failures
  - direct container import probes and the live `30.2` smoke contradict that red result
  - keep this classified as a separate doctor exec-surface anomaly rather than a `30.2` feature failure

## Phase 30.3 Execute Learning

- host/runtime compliance is now carried by three explicit planes instead of implied behavior:
  - a deterministic `output_contract` for objective final-answer constraints
  - receipt-backed memory-operation state and trace
  - truthful lookup-semantics guidance for task-like asks
- the provider now refuses optimistic durable-success language without a committed write receipt
- reset/session teardown is fail-closed for pending explicit writes
- final-answer validation is routed through a host helper seam instead of being buried inside prompt-only policy claims
- the phase stayed within the intended boundary:
  - no task-truth owner was introduced
  - no broad output-rewriter was introduced
  - only mechanical constraints got deterministic post-generation enforcement

## Phase 30.3 Verify Findings

- source surface:
  - `uvx ruff check` stayed green on the touched `30.3` files
  - targeted compliance tests passed:
    - `tests/test_brainstack_phase30_3_compliance.py`
    - `tests/test_install_into_hermes.py`
  - relevant guard suites stayed green:
    - `tests/test_brainstack_phase30_2_residuals.py`
    - `tests/test_brainstack_retrieval_contract.py`
    - `tests/test_brainstack_phase29_style_contract.py`
    - `tests/test_brainstack_real_world_flows.py`
- `hermes-final` surface:
  - the Brainstack payload was reinstalled into `hermes-final`
  - the doctor host-surface check was corrected so it now detects the real `run_agent` helper route for final-output validation
  - the authoritative doctor output now passes the new `final_output_validation` gate
  - direct `hermes-final` interpreter smoke proved:
    - the output validator repairs `U+2014` / emoji / markdown-bold violations
    - explicit user-memory writes end in committed receipts
    - `system_prompt_block()` carries `# Brainstack Truthful Memory Operations`
    - task-like misses render `## Brainstack Lookup Semantics` and do not overclaim committed task records
- live runtime surface:
  - `hermes-bestie` was rebuilt from the updated `hermes-final` checkout and returned healthy
  - the rebuilt container now contains `plugins/memory/brainstack/output_contract.py`
  - the rebuilt `run_agent.py` routes final answers through `apply_brainstack_output_validation(...)`
  - direct container interpreter smoke proved:
    - final-output validation changes the answer when mechanical violations are present
    - the repair count matches the expected objective violations
    - explicit write receipts remain committed in the active runtime
    - `system_prompt_block()` carries the truthful memory-operation contract in the container too
- named non-blocker verification noise:
  - the shell/CLI `brainstack_doctor.py --json` docker dependency false-red remains an exec-surface anomaly, not a `30.3` feature failure
  - broad empty-runtime `prefetch()` smoke inside the container can opportunistically warm Chroma's default embedding cache; that was not used as the authoritative `30.3` gate

## Phase 30.4 Execute Learning

- the architecturally correct resolution for the observed product gap was to make Brainstack the bounded durable owner for explicit task and commitment truth instead of pretending continuity or transcript recall was enough
- task truth stayed narrow and inspectable:
  - title
  - due-date / date-scope
  - optionality
  - status
  - source turn/session
  - ownership metadata
- the provider now commits explicit task capture pre-answer through the same truthful write-receipt discipline introduced in `30.3`, so reset no longer races a delayed background write for obvious task declarations
- relative-date handling is now canonicalized against the user timezone, so Hungarian asks like `mai`, `tegnap`, and `tegnap előtt` resolve through structured lookup instead of fuzzy transcript search
- task-like queries now force structured task lookup before continuity/transcript fallback and explicitly suppress corpus retrieval at the policy layer for that query shape
- the shell `brainstack_doctor.py --json` docker dependency false-red is now closed:
  - docker access failures inside the doctor subprocess are downgraded to warnings instead of being misreported as missing Python dependencies

## Phase 30.4 Verify Findings

- source surface:
  - `uvx ruff check` stayed green on the touched `30.4` files
  - targeted task-memory tests passed:
    - `tests/test_brainstack_phase30_4_task_memory.py`
    - `tests/test_brainstack_phase30_3_compliance.py`
    - `tests/test_brainstack_phase30_operating_context.py`
  - relevant install / retrieval guard suites stayed green:
    - `tests/test_brainstack_retrieval_contract.py`
    - `tests/test_install_into_hermes.py`
- `hermes-final` surface:
  - the Brainstack payload was reinstalled into `hermes-final`
  - shell `brainstack_doctor.py --json` now returns `ok: true` against the docker runtime instead of a false dependency red
- live runtime surface:
  - `hermes-bestie` was rebuilt from the updated `hermes-final` checkout and returned healthy
  - direct container interpreter smoke proved:
    - explicit Hungarian task capture produces a committed Brainstack task-memory receipt
    - reset survives with `rows_after = 3`
    - `Mik a mai napi feladataim?` resolves through structured task truth
    - `corpus_limit = 0` for task-like lookup
    - the working-memory block contains `## Brainstack Task Memory`
    - the authoritative semantics line is present
- named residual kept explicit:
  - an empty temp-runtime provider open inside the container still triggers Chroma ONNX warmup
  - this is no longer hidden, but it remains outside `30.4` because the root cause is eager corpus-backend open, not task-memory correctness

## Phase 30.5 Execute Learning

- the remaining operating-rule reliability bug was not solved by more prompt pressure or more projection tweaks; it required turning the canonical behavior contract into a first-class revisioned truth object
- `behavior_contracts` now carries the durable operating-rule authority, while compatibility reads for `STYLE_CONTRACT_SLOT` resolve through that dedicated storage instead of letting canonical truth live in `profile_items`
- compiled behavior policy remains a derived runtime projection, but its rebuild path is now anchored to the latest committed behavior-contract revision
- explicit behavior-policy correction now creates a superseding canonical revision instead of mutating an implicit profile-lane raw row
- full style-contract recall is now fail-closed: without a committed canonical contract the system may state that truth explicitly, but it may not reconstruct a full rule list from profile fragments or transcript residue

## Phase 30.5 Verify Findings

- source surface:
  - targeted `30.5` source gates stayed green:
    - `tests/test_brainstack_phase29_style_contract.py`
    - `tests/test_brainstack_phase30_2_residuals.py`
    - `tests/test_brainstack_phase30_5_behavior_contracts.py`
  - relevant guard suites stayed green:
    - `tests/test_brainstack_retrieval_contract.py`
    - `tests/test_brainstack_phase30_operating_context.py`
- `hermes-final` surface:
  - the Brainstack payload was reinstalled into `hermes-final`
  - payload parity matched the source package exactly:
    - `source_files = 34`
    - `final_files = 34`
    - `payload_parity = true`
  - direct `hermes-final` interpreter smoke proved:
    - first-class behavior-contract storage is active
    - the first canonical write lands as revision `1`
    - explicit correction advances the canonical revision to `2`
    - the compiled behavior policy follows the latest canonical revision
    - missing full-contract recall fails closed instead of reconstructing from fragments
- live runtime surface:
  - `hermes-bestie` was rebuilt from the updated `hermes-final` checkout and returned `Up (healthy)`
  - direct container interpreter smoke proved:
    - committed canonical behavior-contract storage exists in the rebuilt runtime
    - compatibility reads resolve through the behavior-contract storage key
    - correction supersedes the prior canonical revision and compiled policy tracks the latest revision
    - fail-closed recall blocks fragment-based reconstruction when no committed full contract exists
- named non-blocker runtime noise:
  - Discord slash-command sync still warns that the `skill` command group exceeds Discord's command size limit
  - that warning is orthogonal to the `30.5` behavior-contract truth path and did not affect the verify verdict

## Phase 30.6 Planning Rationale

- after `30.5`, the next architecturally similar authority gap sits in graph truth rather than operating rules
- current live graph ingest still allows raw user/session text to flow toward graph mutation through:
  - `graph_text=user_content` style planning
  - donor graph-adapter forwarding of raw text
  - regex-based candidate extraction in the graph ingress seam
- that is now below the project's stated bar for:
  - truth-first graph authority
  - zero heuristic sprawl
  - multimodal-first architecture
  - long-range accurate relation tracking
- the chosen next phase is therefore:
  - `30.6` `Graph-truth ingest hardening with first-class typed evidence boundary`
- the accepted planning shape is:
  - transcript and corpus may remain raw shelves
  - graph truth becomes a typed-admission shelf
  - graph writes require first-class typed evidence instead of direct raw-text authority
  - Tier-1 graph extraction stays conservative and bounded
  - this phase does not widen into a broad KG or multimodal platform rebuild

## Phase 30.6 Execute Learning

- the right hardening move was not “better graph regexes”; it was to make graph truth stop accepting raw text as authority on the live path
- the new graph evidence boundary now separates:
  - raw transcript / raw corpus shelves
  - typed graph-truth admission
- live ingest planning no longer hands `graph_text` through as a graph-truth write primitive; it emits typed `graph_evidence_items`
- donor graph publication remains intact, but it now sits behind a typed evidence seam instead of direct raw-text parsing
- the live Tier-1 graph path stayed intentionally conservative:
  - only bounded relation/state evidence survives
  - no language-specific regex farm expansion was introduced
- this keeps the phase aligned with:
  - donor-first
  - zero heuristic sprawl
  - truth-first
  - multimodal-first architecture

## Phase 30.6 Execute Findings

- source surface:
  - new typed graph evidence module landed:
    - `brainstack/graph_evidence.py`
  - live ingest and donor boundary were rewritten to use typed graph evidence:
    - `brainstack/extraction_pipeline.py`
    - `brainstack/__init__.py`
    - `brainstack/donors/graph_adapter.py`
    - `brainstack/graph.py`
- source validation:
  - `uvx ruff check` stayed green on the touched `30.6` surface
  - targeted product / guard suites passed:
    - `tests/test_brainstack_graph_ingress.py`
    - `tests/test_brainstack_phase30_6_graph_evidence.py`
    - `tests/test_brainstack_donor_boundaries.py`
    - `tests/test_brainstack_phase30_5_behavior_contracts.py`
    - `tests/test_brainstack_integration_invariants.py::TestBrainstackIntegrationInvariants::test_sync_turn_uses_pipeline_plan_for_durable_admission`
  - combined result:
    - `18 passed, 1 warning`
- named non-blocker source test drift:
  - the broader `tests/test_brainstack_integration_invariants.py` still expects an older Hermes `AIAgent` host shape with `_memory_manager`
  - that host-agent drift is orthogonal to `30.6` graph-truth authority hardening and was not treated as an execute blocker

## Phase 30.6 Verify Findings

- `hermes-final` parity:
  - source and installed final plugin payload matched exactly:
    - `source_files = 36`
    - `final_files = 36`
    - `missing_in_final = []`
    - `extra_in_final = []`
    - `hash_mismatches = []`
- direct `hermes-final` interpreter proof:
  - an isolated temp runtime wrote graph truth from the sentence:
    - `Tomi works on Project Atlas. Tomi is active now.`
  - resulting graph surface:
    - `predicates = ["status", "works_on"]`
    - `search_count = 2`
    - `state_count = 1`
    - `no_noise_write = true`
  - this proved that typed graph evidence was present and that an unrelated noise turn did not create extra graph truth
- rebuilt live runtime proof:
  - `./scripts/hermes-brainstack-start.sh rebuild` completed cleanly
  - `hermes-bestie` came back `Up (healthy)` on new image id:
    - `sha256:ca6360281d63a63933d2cdb0e742d011e9f2c1a672900d72ba4ffdfa4689b49d`
  - the running container payload now contains `graph_evidence.py`
- direct container interpreter proof:
  - used `/opt/hermes/.venv/bin/python` inside the rebuilt container against an isolated temp runtime
  - result:
    - `rows_after_fact = 2`
    - `rows_after_noise = 2`
    - `states_after_fact = 1`
    - `states_after_noise = 1`
    - `predicates = ["status", "works_on"]`
    - `no_noise_write = true`
- verify verdict:
  - `30.6` is now closed green across source, `hermes-final`, and rebuilt live runtime surfaces

## Phase 31 Planning Rationale

- the live regression after `30.5`/`30.6` is not one vague “memory got worse” problem
- the accepted cross-agent reading now has three concrete seams:
  - the active canonical behavior contract can become partial and still remain authoritative
  - explicit multi-message rule teaching does not converge into one committed canonical revision
  - Brainstack-only tool blocking is not uniformly wired across all live tool-execution paths
- this phase exists to freeze the evidence-backed root-cause model before writing the hotfix

## Phase 32 Planning Rationale

- once the root-cause model is frozen, the next correct step is a production hotfix, not a broad redesign
- the hotfix must directly close the three proven breakpoints:
  - canonical contract protection against weaker `tier2_llm` supersession
  - multi-message convergence for explicit user rule teaching
  - sequential-path tool blocking parity with the already-patched concurrent path
- `session_search` misuse stays inside this same hotfix surface because it is part of the same live degradation path

## Phase 36 Planning Rationale

- after `34` and `35`, the primary remaining product pain is no longer truth ownership itself
- the remaining gap is packet assembly quality:
  - too many rendered sections
  - too much shelf overlap
  - too much duplicated factual rendering
  - too much layered authority framing between Brainstack and host/runtime seams
- the accepted reading is:
  - `34` improved role split
  - `35` improved operating truth
  - but the ordinary-turn memory packet is still assembled as concatenated sections rather than as a deduplicated owner-arbitrated render
- therefore the next correct step is not another behavior phase and not another storage phase
- it is a packet-collapse phase that targets:
  - owner arbitration before rendering
  - cross-section dedupe
  - continuity/transcript collapse
  - wrapper-note collapse
  - preserved exact recall and fail-closed honesty
- the accepted refinement is:
  - packet quality must be judged on the combined hot path:
    - system substrate
    - working-memory block
    - host/runtime memory boundary
  - the phase therefore includes explicit packet-quality regressions rather than only truth-integrity proof

## Phase 37 Planning Rationale

- the latest live audit shows a narrower but more dangerous failure than packet noise alone:
  - canonical style-contract capture can ingest conversational framing
  - stale rule-count headings can survive later explicit user convergence
  - the compiled hot-path policy can rebuild itself from already-polluted canonical truth
  - reset then faithfully replays corrupted authority instead of the user’s final intent
- the accepted reading is:
  - this is not primarily a recall bug
  - this is not primarily a packet-collapse bug
  - this is a canonical style-contract capture and promotion bug
- therefore the next correct step is not another broad behavior phase and not another storage phase
- it is a bounded canonical-contract sanitization phase that targets:
  - explicit contract extraction without conversational contamination
  - narrow patch-lane semantics
  - polluted-canonical-row quarantine or repair
  - compiled-policy promotion safety
  - reset-proof exact recall of the final user-authored contract
- the accepted refinement is:
  - multi-message explicit rule teaching must remain possible
  - but raw fragment concatenation can no longer be trusted as the canonical promotion surface
  - the fix must prefer structural cleanliness and auditable repair over prompt-time masking
  - the same phase should also restore semantic fidelity for punctuation invariants, because the current `dash` handling can contradict explicit user intent

## Phase 38 Planning Rationale

- after `35`, the operating substrate is real enough that its remaining weaknesses are now correctness bugs, not just maturity gaps
- the accepted reading is:
  - `current_commitment` and `next_step` still risk silent overwrite through singleton stable-key semantics
  - operating/task capture remains too structured-input dependent for natural conversation
- therefore the next correct step after `37` is not another packet phase
- it is a bounded operating-memory correctness phase that targets:
  - append-safe persistence
  - stable-key multiplicity correctness
  - bounded natural-chat promotion
- the accepted refinement is:
  - this must stay narrow and donor-first
  - it must not drift into planner behavior, cue-farm parsing, or ontology growth

## Phase 38.1 Planning Rationale

- after `38`, the next clearly proven residual is not graph breadth first
- the accepted reading is:
  - `control_plane` still uses cue lists too centrally for packet shaping
  - this violates the intended owner-first direction even if packet quality improved in `36`
- therefore the next correct step before resuming graph-side work is a bounded control-plane phase that targets:
  - owner-first routing signals
  - cue-list de-escalation
  - packet shaping based on retrieval support rather than query-shape guessing
- the accepted refinement is:
  - this must not become a broad retrieval rewrite
  - this must not replace cues with another opaque heuristic layer
  - cues may remain only as narrow boundary fallback where no stronger owner signal exists

## Phase 39 Planning Rationale

- once packet quality, canonical style-contract correctness, and control-plane cue-first routing are tightened, the next accepted graph residual is boundary hardening rather than local semantic widening
- the accepted reading is:
  - the typed graph boundary is already the correct write seam
  - the immediate missing piece is clearer contract proof, ingress observability, and explicit fail-closed behavior
- therefore the next correct step after `38.1` is a bounded graph-boundary phase that targets:
  - typed ingress contract clarity
  - provenance and receipt observability
  - source / install / runtime parity on fail-closed graph truth
- accepted non-phase-promoted residuals remain:
  - donor-backed semantic widening beyond the current narrow extractor
  - controlled degrade-open seams
  - these are real, but not ahead of the currently proven correctness bugs above

## Full-repo critical and high audit after Phase 39

- critical:
  - `prefetch()` still attempts style-contract mutation from the user query itself:
    - [__init__.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/__init__.py#L843)
    - accepted reading:
      - a nominal read surface can still enter the canonical style-contract write seam
      - this is incompatible with long-term read/write separation and directly explains why rule-recall queries can mutate authority
- high:
  - compiled behavior policy self-healing is incomplete:
    - [db.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/db.py#L2790)
    - [db.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/db.py#L2985)
    - accepted reading:
      - if the compiled row is missing or was fail-closed deleted, same-content behavior-contract writes return early and do not rebuild it
      - retrieval can remain stuck on fallback contract assembly even when canonical text is otherwise usable
  - ordinary-turn contract projection can diverge from exact canonical recall:
    - [retrieval.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/retrieval.py#L395)
    - [retrieval.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/retrieval.py#L351)
    - accepted reading:
      - when compiled policy is absent, the active communication lane falls back to profile and graph rows
      - exact style-contract recall remains tied to canonical archival content
      - the same principal can therefore surface two different behavior truths
  - style-related historical residue is not reconciled when canonical contract truth changes:
    - [db.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/db.py#L2738)
    - [retrieval.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/retrieval.py#L418)
    - accepted reading:
      - canonical behavior-contract writes do not clean up stale style-oriented profile rows
      - fallback active-lane rendering can continue to read outdated preference atoms even after canonical truth changes
  - route-resolution dependency failure still degrades open:
    - [executive_retrieval.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/executive_retrieval.py#L520)
    - accepted reading:
      - route-hint failure is logged and converted into fallback fact mode
      - live runtime already proved this can happen through missing optional dependencies
  - transcript-derived durable preference writes still rely on cue-farm logic:
    - [profile_contract.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/profile_contract.py#L140)
    - [profile_contract.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/profile_contract.py#L197)
    - [tier2_extractor.py](/home/lauratom/Asztal/ai/atado/Brainstack/brainstack/tier2_extractor.py#L713)
    - accepted reading:
      - this is still a core durable-write surface using phrase triggers and slot expansion
      - it is strong enough to create or preserve long-lived style residue

## Phase 40 Planning Rationale

- after `39`, the next accepted blocker is not graph breadth, packet cosmetics, or another style-only patch
- the accepted reading is:
  - the core remaining integrity problem is now cross-surface memory authority divergence
  - one principal can carry:
    - polluted canonical contract history
    - missing compiled policy
    - stale style-related profile residue
    - read-side mutation risk across multiple truth owners
    - and no deterministic out-of-band operator truth snapshot tying them together
  - a wipe is useful for clean repro, but not a permanent fix
- therefore the next correct step after `39` is a bounded integrity phase that targets:
  - global transaction boundary hardening
  - historical repair
  - anti-regeneration for style authority
  - generation-linked read-path convergence
  - deterministic out-of-band proof
- accepted refinement:
  - this phase must not solve the problem with more heuristics, broader prompt steering, or text-only packet hacks
  - this phase must not be reduced to a style-only fix
  - this phase must give the runtime one convergent, auditable authority lane across canonical contract, compiled policy, and ordinary-turn active communication support
  - transcript/profile style residue must not be able to re-grow contract-shaped authority once canonical style truth exists
  - additional high residuals remain real but out of scope for this phase:
    - owner-first routing completion and route-resolution fail-closed convergence
    - broader durable preference ingress hardening beyond the anti-regeneration seam
    - graph value frontier work beyond typed ingress integrity
  - those should be tracked as explicit follow-up phases rather than smuggled into this integrity phase

## Phase 41 Planning Rationale

- after `40.3`, the next need is not another narrow local fix but a complete inspector-grade inventory of all remaining debt, defects, residual heuristics, fallback seams, proof gaps, deploy drifts, and principle-compliance breaks
- accepted reading:
  - this phase must go deeper than the already-known residual list
  - it must cover:
    - source code
    - runtime/deploy behavior
    - routing and retrieval seams
    - memory authority and fallback seams
    - graph and legacy compatibility surfaces
    - test and proof gaps
    - config/auth/environment drift
    - roadmap/planning mismatch if any
  - it must preserve findings incrementally so context compaction cannot erase detail
- the first already-proven runtime findings entering the phase are:
  - Discord slash command sync failure caused by oversized `/skill` payload
  - OpenRouter `402` payment failures on route-resolution and auxiliary memory paths
  - CA bundle path drift warning for Hermes auth/runtime TLS
- this phase should reference the immutable principles directly rather than paraphrasing them

## Post-41 Corrective Program Rationale

- the `41` audit findings are too broad and too structurally important to collapse into one “cleanup” phase
- the corrective work must be split by dependency order, not by convenience bucket
- accepted reading:
  - `42` closes residual memory routing and authority convergence debt first
  - `43` reduces live runtime fallback and boot compatibility seams
  - `44` retires legacy storage/config/compatibility debt that keeps ambiguity alive
  - `45` attacks the giant orchestration hubs and bridge-node blast radius
  - `46` builds the inspector-proof replay and evidence harness on top of the corrected structure
  - `47` restores product value frontier through producer-aligned typed graph and multimodal expansion without reintroducing heuristic sprawl
- this is intentionally not an MVP or beta rescue ladder
- the target is a masterpiece-grade remediation program with:
  - integrity
  - inspectability
  - modularity
  - proof
  - value recovery
- all follow-up phases must continue to reference:
  - `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`

## Phase 48 Stabilization Rationale

- the live Bestie incident proved that code-side cleanup alone is not enough if live authority bootstrap, compiled enforcement, natural recall routing, transcript persistence, user-surface hygiene, and scheduling correctness do not converge in one runtime path
- the accepted reading is:
  - the user plans to wipe the polluted live memory store
  - that wipe is a reset aid, not the permanent solution
  - the permanent solution is one ordered stabilization phase that closes the whole live-chat failure chain after reset:
    - authority bootstrap and compiled-policy presence
    - final-output typed invariant enforcement
    - owner-first implicit style recall
    - transcript persistence correctness
    - tool-trace containment
    - reminder timezone correctness
- this phase is intentionally not benchmark work for one conversation
- it is the product-stabilization gate that must make ordinary live chat trustworthy after a clean reset
- all artifacts in this phase must continue to reference:
  - `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`

## Phase 49 Stabilization Loop Rationale

- the post-48 live chat evidence shows a second gap:
  - local correctness can improve while the user-facing product still feels worse
  - the root cause is cross-layer sequencing drift, not just one missing fix
- the accepted reading is:
  - internal Brainstack blocker text leaking to the user is a product failure, not acceptable fail-closed behavior
  - local unit or slice verification is no longer enough as the main quality gate
  - the next step must freeze feature growth and move to a replay-driven correction loop on real failing chats
- therefore `49` is intentionally a no-feature corrective phase:
  - build a bounded replay pack from real failing Bestie conversations
  - run it on the live-style docker/runtime path
  - fix only the minimum cross-layer defects needed to make the replay pack pass
  - rerun the whole pack after every correction
- the expected recovery targets are:
  - no blocked-output leak to the user
  - no tool-trace leak to the user
  - style-authority recall works on natural questions
  - authority bootstrap and final-output enforcement stay converged on the live path
  - transcript persistence and reminder timezone behavior are stable on the same runtime path
- this phase is not benchmark work and not capability expansion
- it is a product-recovery gate whose success criterion is dependable ordinary chat behavior after repeated iterative churn
- all artifacts in this phase must continue to reference:
  - `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`

## Phase 51 Synergy Audit Rationale

- after the donor-first de-escalation recovery, the next unresolved question is no longer “can Brainstack be made thinner?”
- the real question is:
  - does the rebuilt Brainstack plugin genuinely help Hermes as a memory provider
  - or does it only look thin while staying hard to inspect, hard to prove, and oversized behind the seam
- the accepted reading is:
  - seam fit and product fit are different questions
  - passing local integration tests is necessary but not sufficient proof of real synergy
  - graph evidence, blast radius, bridge/hub pressure, and inspectability all matter for this verdict
- the early graph findings already freeze several important facts:
  - `agent/memory_manager.py` is still a genuinely thin orchestration seam and its provider failures remain non-fatal
  - `run_agent.py::AIAgent.run_conversation` remains a major host hub, so any memory integration that thickens this path is architecturally dangerous
  - the current Brainstack plugin files are large and operationally central enough to merit direct donor-fit scrutiny
  - the code graph does not cleanly surface `plugins/memory/brainstack/__init__.py` as a queryable node even after a full rebuild, which is itself an inspectability gap
- therefore the next audit must answer two separate truths:
  - where Brainstack is already truly synergistic with Hermes
  - where the current integration is still only paper-synergistic because proof, decomposition, or inspectability is weak
- this phase is not feature work
- it is a truth-first donor-fit judgment gate before any further product claims
- all artifacts in this phase must continue to reference:
  - `/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-latest/.planning/IMMUTABLE-PRINCIPLES.md`

## Phase 36 Execute Findings

- source surface:
  - `brainstack/retrieval.py` now builds and reuses a shared system-substrate projection instead of treating the substrate and working-memory render as unrelated surfaces
  - `brainstack/control_plane.py` now threads that substrate signature into working-memory assembly
  - `brainstack/__init__.py` now computes the same substrate projection for both system-prompt tracing and prefetch packet suppression
  - `scripts/install_into_hermes.py` now patches the host memory-wrapper note to softer support wording instead of a stronger authority-upgrade phrase
- combined packet collapse:
  - duplicate ordinary-turn contract rendering is suppressed when the same bounded invariant lane is already present in the system substrate
  - stable profile keys already rendered by the substrate are suppressed from the working-memory block
  - `Evidence Priority` is suppressed from the working-memory block when the substrate already carries `Truthful Memory Operations`
  - system-substrate profile duplication inside the operating-context + profile surfaces is collapsed
  - recent continuity is suppressed when matched continuity already covers the same turn
  - transcript overlap is suppressed against continuity evidence with a bounded “keep one row” fallback so the channel does not silently disappear
- source validation:
  - changed-surface `ruff` checks are green
  - targeted packet-collapse / retrieval / transcript / installer suite:
    - `34 passed, 1 warning`
  - broader guard across phase `30.2`, `30.3`, `35`, and older packet-proof seams:
    - `52 passed, 1 warning`
- named non-blocker:
  - `tests/test_brainstack_real_world_flows.py` still fails collection because it imports the legacy `plugins.memory.brainstack` seam
  - this harness drift predates Phase 36 and was not treated as a source execute blocker

## Phase 31 Execute Findings

- live session trace proof:
  - session `20260419_004115_620afb8e` used `session_search` to answer the full-rule recall request
  - later in the same session the runtime invoked:
    - `skill_manage(action=create, name=29-rules-style-contract, category=dogfood)`
- host/runtime path proof:
  - the captured `skill_manage` call arguments should have been blocked by the installed Brainstack-only blocker
  - the installed `run_agent.py` applies that blocker only in the concurrent `_invoke_tool(...)` path
  - the sequential path still calls `handle_function_call(...)` directly without the same blocker
  - accepted reading:
    - Brainstack-only tool blocking is half-wired across execution modes
- canonical contract proof:
  - the active live `behavior_contract` row is:
    - `revision_number = 3`
    - `status = active`
    - `source = tier2_llm`
    - `content_len = 1478`
  - all recorded revisions for this principal scope are also `tier2_llm`-authored
  - accepted reading:
    - the full `29`-rule pack never became an explicit user-authored canonical revision
    - the active authority is a partial Tier-2 contract
- compiled policy proof:
  - the installed compiled behavior policy reports:
    - `raw_rule_count = 14`
    - `status = active`
    - `truncated = false`
  - accepted reading:
    - the product did not merely “recall badly” from a good canonical source
    - it was obeying and recalling from already-partial canonical truth

## Phase 55 Execute Findings

- host explicit-truth capture:
  - the paired naming-truth guidance was tightened so the native explicit seam persists the full naming set instead of intermittently dropping the assistant self-name
  - the successful `target='user'` tool result continues to collapse back to compiled user-index truth instead of echoing raw entries into the next model turn
- targeted source validation:
  - focused regression ring for prompt-builder, memory-tool, and run-agent seams:
    - `6 passed`
- live/provider proof:
  - script:
    - `/home/lauratom/Asztal/ai/finafina/scripts/phase55_live_uat.py`
  - artifact:
    - `/home/lauratom/Asztal/ai/finafina/hermes-config/bestie/runtime/phase55-live-uat.json`
  - result:
    - `round_count = 2`
    - `total_failures = 0`
    - `all_green = true`
  - proof surface:
    - real provider
    - Discord-shaped runtime path
    - fresh mutable state on each run
    - same-session and post-reset explicit-pack recall
    - ordinary-turn surface checks
- runtime state:
  - validated model:
    - `google/gemini-3-flash-preview`
  - provider:
    - `nous`
  - rebuilt `hermes-bestie` runtime:
    - `running; connected=discord`
- behavior-authority reading:
  - final proof runs still showed:
    - `behavior_contract_count = 1`
    - `behavior_policy_count = 0`
  - accepted reading:
    - raw archival explicit-pack storage can remain
    - compiled behavior-policy re-growth did not happen
    - ordinary-turn governance drift did not reappear
- accepted closure:
  - the remaining product gap for explicitly taught rule-pack fidelity and clean ordinary-turn compliance is closed on the live provider path
  - this was achieved without:
    - new behavior-governor logic
    - locale-specific extraction
    - rule-pack-specific regex farming
    - reply-time patching

## Phase 56 Planning Trigger

- post-Phase-55 live audit on the installed `finafina` runtime surfaced inspector-blocking defects that were not eliminated by the fresh-state proof alone
- accepted findings:
  - deployed `USER.md` is still degraded and non-canonical
  - active `behavior_contracts` and `compiled_behavior_policies` still exist for the explicit native rule pack
  - internal runtime status text entered transcript memory as assistant content
  - the remaining proof gap is now source-of-truth install reproducibility plus deployed-state cleanup, not another broad memory-design question
- accepted correction:
  - the remaining defect is not described merely as dirty deployed state
  - it is also active authority residue that still violates the kernel/mirror target shape
  - the next proof must distinguish:
    - installed runtime / provider-path proof
    - real Discord UI proof
- accepted planning correction:
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50` becomes the only source-of-truth code surface for the next fix
  - `/home/lauratom/Asztal/ai/finafina` is treated as an installed runtime target only
  - the next phase must prove that a fresh Hermes checkout can be brought to the corrected state by the wizard/install path from the source-of-truth repo
  - after this phase, the project should default to stabilization / debt paydown rather than new capability work unless a separate deliberate decision says otherwise

## Phase 57 Planning Trigger

- post-Phase-56 live Discord testing on the installed `finafina` runtime surfaced a new inspector-blocking defect family in the active runtime path
- accepted findings:
  - an ordinary Discord turn (`Mondj 3 budapesti hidat.`) produced no reply and stayed live until manual `/reset`
  - the same runtime window logged:
    - `Memory provider 'brainstack' initialize failed: std::bad_alloc`
    - repeated `KuzuGraphBackend is not open`
  - a bare `Session reset.` message still reached the user-facing Discord surface
  - reminder / cronjob acknowledgements are not yet trustworthy:
    - the bot can claim a reminder was created
    - but the requested near-term wake-up may still not arrive
    - this means scheduler truth and/or delivery proof remains open
- accepted diagnosis:
  - the remaining defect is not framed as a pure Brainstack blame claim
  - it is a live-runtime correctness family spanning:
    - stuck-run recovery
    - half-open graph/provider containment
    - scheduler truthfulness
    - reset surface hygiene
  - the next phase must separate root cause from containment and fix both without heuristic drift
- accepted planning correction:
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50` remains the only code source of truth
  - `/home/lauratom/Asztal/ai/finafina` remains an install-and-proof target only
  - the next proof must include real Discord UI evidence for:
    - no ordinary-turn hang
    - no fake scheduler success
    - no reset leak
  - this remains stabilization / debt paydown work, not new capability work

## Phase 58 Planning Trigger

- post-Phase-57 cleanup and the subsequent `croniter` wizard fix clarified that the remaining debt is no longer primarily runtime breakage
- accepted findings:
  - the source-of-truth repo still carries unreleased dirty fixes in:
    - `brainstack/__init__.py`
    - `brainstack/db.py`
    - `scripts/brainstack_doctor.py`
    - `scripts/install_into_hermes.py`
  - the live installed runtime still carries persistent-state residue:
    - at least one old `Operation interrupted: ...` transcript row
    - at least one old superseded `behavior_contract` row
  - the source repo still contains large half-demoted or effectively dead-looking shipped surfaces that need explicit keep/remove decisions
  - planning still carries stale or open-seeming critical/high wording and manual-gate language that no longer cleanly matches the actual runtime and release story
- accepted diagnosis:
  - the next phase is not new capability work
  - it is inspector-readiness debt paydown across:
    - source-of-truth release closure
    - persistent-state scrub
    - half-wired surface reduction
    - planning/proof normalization
  - automated dead-code signals are useful smoke but not sufficient proof for deletion; runtime-entry validation must gate removals
- accepted planning correction:
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50` remains the only code source of truth
  - `/home/lauratom/Asztal/ai/finafina` remains an install-and-proof target only
  - the next phase must end with:
    - clean releasable source repo
    - clean persistent state on the installed runtime
    - explicit keep/remove decisions for half-wired shipped surfaces
    - normalized planning artifacts that match the actual proof story

## Phase 58 Execution Result

- accepted closure:
  - the source-of-truth installer now scrubs runtime transcript contamination and style-contract behavior residue
  - the doctor now checks runtime DB hygiene directly, not only static install wiring
  - the installed `finafina` runtime now shows:
    - `interrupt_transcript_hits = 0`
    - `style_contract_behavior_rows = 0`
    - `compiled_behavior_policies = 0`
    - canonical `USER.md`
- accepted half-wired surface decisions:
  - `host_payload/agent/brainstack_mode.py` remains only as a bounded compatibility shim
  - installer legacy regexes remain only as migration-time canonicalization helpers
  - `behavior_policy.py` remains because it is still runtime-referenced, but explicit rule-pack authority no longer lands there
- accepted validation:
  - source files `py_compile`: pass
  - targeted `finafina` ring:
    - `tests/agent/test_brainstack_phase50_integration.py`
    - `tests/cron/test_jobs.py`
    - `tests/cron/test_cron_inactivity_timeout.py`
    - `tests/gateway/test_flush_memory_stale_guard.py`
  - result:
    - `76 passed in 5.39s`
- accepted planning correction:
  - Phase 58 closes the inspector-readiness debt family it opened
  - the default next mode remains stabilization / debt paydown, not new capability build

## Phase 59 Planning Trigger

- a new user-facing complaint now centers on context pressure rather than runtime breakage:
  - "`Hermes fills up the context windows so quickly`"
- accepted verified current facts:
  - host prompt assembly in `finafina` is composite and large even before Brainstack packetization:
    - large prompt-builder guidance blocks
    - builtin memory block
    - builtin user-profile surfaces
    - context files and tool schemas where applicable
  - Brainstack is still a real contributor because it adds:
    - a provider system-prompt block
    - a per-turn prefetch packet
  - current Brainstack budgeting is bounded and route-aware, but still fragmented by shelf rather than governed by one explicit cross-shelf allocator
  - current hybrid retrieval already mixes keyword and semantic signals, but the fusion is not yet strong enough to treat as solved
- accepted diagnosis:
  - the next phase must not assume the complaint is purely a Brainstack defect
  - it must start with attribution and only then improve the Brainstack-owned part
  - the highest-value Brainstack-owned follow-up is:
    - cross-shelf budget allocation
    - hybrid retrieval fusion hardening
  - this remains quality/efficiency work, not donor churn and not a new capability lane

## Phase 59 Execution Result

- accepted attribution result:
  - the current fast context-fill complaint is not truthfully attributable to Brainstack alone
  - the Hermes host stack remains large before Brainstack packetization
  - live-adjacent Bestie proof showed Brainstack selecting only `3-5` evidence rows for the tested queries
- accepted Brainstack-owned correction:
  - `WorkingMemoryPolicy` now carries `evidence_item_budget`
  - executive retrieval now applies one shared cross-shelf evidence cap in addition to shelf-local caps
  - hybrid fusion now uses weighted channel/shelf contributions plus explicit multi-channel agreement bonus
  - transcript-only bias was reduced so multi-signal candidates can win when justified
- accepted install/runtime proof:
  - source-of-truth installer reproduced the changes onto `/home/lauratom/Asztal/ai/finafina`
  - runtime rebuild returned `running; connected=discord`
  - docker-mode doctor passed after install
- accepted validation:
  - touched source files `py_compile`: pass
  - synthetic fusion proof:
    - multi-channel continuity candidate ranked above transcript keyword-only candidate
  - synthetic allocator proof:
    - `evidence_item_budget = 3` -> selected evidence rows `= 3`
    - `evidence_item_budget = 5` -> selected evidence rows `= 5`
- accepted closure:
  - Phase 59 is a bounded quality/efficiency uplift
  - it closes without donor churn, backend-swap theater, or heuristic sprawl

## Phase 60 Planning Trigger

- new real-world Discord use surfaced a mixed bug cluster while the user was trying to use the system normally, not while synthetic testing it
- the user then explicitly narrowed the architectural intent:
  - Phase 60 must target Brainstack-universal defects only
  - the current live Discord thread is a case study and evidence source, not the design target
  - Hermes-native bugs may be documented as boundary conditions, but the phase must not turn into a generic Hermes bugfix pass
- accepted verified findings to preserve:
  - the busy-ack string
    - `⚡ Interrupting current task (...) I'll respond to your message shortly.`
    comes from the gateway run loop
  - the empty-after-tools warning
    - `⚠️ Model returned empty after tool calls — nudging to continue`
    comes from the run-agent loop
  - the live session artifact shows repeated background-process launches, path mismatches (`./tools`, `/workspace/tools`, actual `/opt/data/tools`), interrupted `execute_code` turns, and repeated completion injections in the same Discord thread
  - the stale `11:15 van, indulnod kell elvinni a kaját` statement was not backed by the active current scheduler store at the time it resurfaced
  - the same stale reminder text still existed in:
    - live session history
    - Brainstack transcript rows
    - Brainstack continuity rows
  - later live forensics also showed:
    - the hourly `Brainstack Pulse Daemon` cron session did not recreate the food reminder
    - its stored output ended with `HEARTBEAT_OK`
    - the stored evidence does not yet prove a preserved assistant-origin `Cron job 'Kaja elvitele emlékeztető' created` line; what is preserved is the user's complaint about seeing it
    - nevertheless the system promoted assistant-authored self-diagnosis and narrative into durable continuity rows as if they were trustworthy facts
  - broader same-day runtime review also showed:
    - `std::bad_alloc -> SQLite fallback` is still happening repeatedly in live operation, not only as an old one-off
    - injected reflection prompts are appearing in ordinary Discord sessions and causing real `memory` / `skill_manage` writes
    - at least one cron session preserved a real runtime/tool failure and still ended as `HEARTBEAT_OK`
    - at least one live reminder cleanup removed the wrong job target
    - preserved cron sessions still expose a broader tool surface than a minimal safe cron execution path
    - newer continuity rows are also promoting speculative assistant implementation claims into durable facts, including dynamic 2-minute heartbeat behavior and package-management workaround narratives
    - the final re-check confirms that the 2-minute heartbeat is no longer only narrative contamination; it is now the real active live cron configuration (`Brainstack Dynamic Pulse (SOTA)`)
- accepted diagnosis:
    - the phase must separate:
      - Brainstack-owned universal defects
      - host/runtime noise that merely produced contaminated inputs
      - wizard seam concerns only where Brainstack correctness across installs requires them
    - the currently accepted Brainstack-universal targets are:
      - expired reminder/task text resurfacing as current truth in an ordinary turn
      - durable extraction over-trusting assistant-authored self-explanation in noisy live threads
      - the same over-trust promoting speculative implementation-status claims into durable state
      - reflection-driven writes being treated too much like ordinary user-authored truth when Brainstack forms durable state
    - the currently accepted host/runtime boundary findings are:
      - execute-code interruption and background-process completion churn
      - generic provider/runtime failures
      - generic scheduler mechanics unless Brainstack later persists or projects their byproducts as trusted truth
    - live cron configuration drift has become real state, not just assistant talk, but it only belongs to Phase 60 insofar as Brainstack persists, projects, or over-trusts it
    - the next phase must preserve and then resolve the Brainstack-owned universal defects without collapsing the whole live thread into one fake root cause

## Phase 60 Execution Outcome

- frozen architecture decision:
  - temporal grounding:
    - structured-lane-first task authority
  - provenance/trust:
    - Tier-2 durable extraction now consumes user-authored evidence only from merged turn rows
  - reflection-path:
    - minimal write-origin seam added so Brainstack can fail closed on `background_review` built-in memory writes
- source-of-truth Brainstack changes:
  - transcript helper now exposes role split helpers for merged turn rows
  - Tier-2 transcript batching now emits user-only evidence blocks
  - transcript evidence rendering now shows primary user content instead of user+assistant combined snippets
  - task-like retrieval now suppresses continuity/transcript fallback when structured task authority is active outside temporal-route queries
  - task follow-up date cues now share the same day-family vocabulary as due-date extraction, closing the Hungarian `holnap` / `holnapi` routing gap for obligation-style follow-up asks
  - `on_memory_write(...)` now accepts optional metadata and skips Brainstack durable mirroring for `write_origin=background_review`
  - task capture now requires a genuinely task-shaped headed list instead of any multi-line prose block containing task cues
- minimally necessary host seam:
  - `run_agent.py` tags background-review memory writes with `write_origin=background_review`
  - `memory_manager.py` forwards optional metadata and falls back cleanly for legacy provider signatures
  - `memory_provider.py` documents the optional metadata parameter
- live proof after install into `veglegeshermes-source`:
  - assistant-prefixed continuity contamination rows: `0`
  - reflection prompt continuity rows: `0`
  - reflection prompt transcript rows: `0`
  - Phase 60 planning-prose task pollution rows: `0`
  - task-like lookup proof on `Milyen feladataim vannak holnapra?`:
    - `task_like = true`
    - `task_rows = 0`
    - `matched = 0`
    - `recent = 0`
    - `transcript_rows = 0`
    - working-memory block now reports structured miss without continuity/transcript fallback
  - follow-up task query variants now also resolve through the structured task path:
    - `Mit kell holnap csinálnom?`
    - `Holnap mit kell csinálnom?`
    - `Mi a holnapi teendőm?`
    - each now produces `task_like = true` with `task_rows = 0`, `matched = 0`, `recent = 0`, `transcript_rows = 0`
  - reflection-skip proof on temp DB copy:
    - background-review write created `0` profile/continuity rows
    - equivalent ordinary explicit user write still created the expected mirrored profile row
- live cleanup performed because pre-fix contaminated state would otherwise invalidate proof:
  - deleted reflection-prompt transcript rows
  - deleted reflection-prompt continuity rows
  - deleted assistant self-claim continuity rows
  - deleted task-memory rows created from the Phase 60 planning paste and reflection-prompt sessions
- residual note:
  - older native-profile mirror rows may still contain judgment-heavy statements whose original write provenance is not recoverable from existing metadata
  - these were not bulk-deleted in Phase 60 because they are not cleanly distinguishable from legitimate explicit user-taught entries in the current historical store

## Phase 61 Planned Focus

- new critical Brainstack-owned finding:
  - after restart, a broad recap question about immediately preceding work can still produce an effectively empty Brainstack packet even when relevant `continuity_events` and `transcript_entries` exist in the live DB
- live evidence gathered so far:
  - Brainstack plugin is active
  - `sidecars.rtk.enabled = false`, but that alone does not explain the failure
  - live DB contains `phase 60`-related continuity/transcript rows
  - live DB contains no useful `operating_records` for that recent work
  - transcript FTS can find simpler normalized matches like `phase 60` and `brainstack`
  - the recap packet for a real restart question still comes back with:
    - `continuity_rows = 0`
    - `operating_rows = 0`
    - `task_rows = 0`
    - `transcript_rows = 0`
    - only `profile_rows = 1`
- accepted root-cause model for Phase 61 planning:
  - this is not primarily a `session_search` problem
  - `session_search` is the visible symptom after Brainstack recap recall fails
  - the deeper Brainstack defect is:
    - missing/weak durable recent-work operating truth
    - plus recap routing that is too literal and under-projects existing stored evidence
- Phase 61 therefore exists to fix:
  - restart-surviving recent-work recall
  - durable operating-summary authority
  - session-search demotion to secondary transcript-detail recovery

## Phase 61 Execution Outcome

- source-of-truth changes landed in:
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/structured_understanding.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/task_memory.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/operating_truth.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/control_plane.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/executive_retrieval.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/tier2_extractor.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/__init__.py`
- the active Brainstack task / operating / recent-work path no longer uses code-level cue tables or phrase-match routing
- restart recap now relies on:
  - principal-scoped `operating_records`
  - session provenance already present in the operating lane
  - ongoing operating capture plus recent-work consolidation
- `prefetch()` stays read-only and no longer runs task/operating capture inference on the query text
- the native aggregate phrase-planner was disabled pending a structured non-heuristic replacement
- the live Tier-2 logistics regex supplement was removed from the active extraction path; only historical DB migration compatibility code still references it
- install / runtime reproduction on `/home/lauratom/Asztal/ai/veglegeshermes-source`:
  - doctor: pass
  - payload parity: `39/39` files match source-of-truth with no non-`__pycache__` drift
  - runtime after rebuild: `running; connected=discord`
  - container health: `healthy`
  - restart count: `0`
- targeted regression ring rerun after the final rebuild:
  - `tests/agent/test_memory_provider.py`
  - `tests/run_agent/test_memory_provider_init.py`
  - `tests/tools/test_session_search.py`
  - `tests/cron/test_jobs.py`
  - `tests/cron/test_scheduler.py`
  - `tests/cron/test_cron_inactivity_timeout.py`
  - `tests/gateway/test_flush_memory_stale_guard.py`
  - result: `265 passed in 6.98s`
- accepted residual:
  - no manual Discord round-trip UAT was performed inside the Phase 61 closeout
  - historical logistics regex compatibility remains only in `db.py` migration paths, not in the live extraction path

## Phase 61.1 Planned Focus

- new critical Brainstack-owned finding:
  - the `v1.0.17` no-heuristic transition is directionally correct but currently too fragile, because too much ordinary Brainstack behavior depends on successful live `structured_understanding` calls
- validated evidence:
  - current source routes task lookup, operating lookup, task capture, operating capture, and route analysis through `structured_understanding.py`
  - `prefetch()` is intentionally read-only, but `sync_turn()` still performs automatic task/operating capture
  - recent live logs show repeated Brainstack structured-understanding failures, including:
    - timeouts
    - `400 Invalid input`
    - `402` credit-related failures
- accepted root-cause model for Phase 61.1 planning:
  - the problem is not that heuristics were removed
  - the problem is that the new structured seam now carries too much ordinary-kernel availability and correctness authority too early
  - therefore the correct move is neither:
    - full rollback to `v1.0.16`
    - nor feature churn on top of `v1.0.17`
  - the correct move is:
    - stabilize the current architecture in place
    - reduce the structured-understanding blast radius
    - preserve the no-heuristic direction
- Phase 61.1 therefore exists to fix:
  - structured-understanding availability bounds
  - explicit fact-safe degraded mode
  - narrowed mandatory dependence on live understanding success
  - release discipline before Phase 62

## Phase 61.1 Execution Outcome

- source-of-truth changes landed in:
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/structured_understanding.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/executive_retrieval.py`
- the stabilization did not restore heuristics and did not roll back to `v1.0.16`
- success caching and failure handling are now separated in the structured-understanding seam, so degraded responses are not cached as if they were successful understanding results
- repeated/hard failures now open a bounded degraded mode:
  - query understanding degrades to explicit fact route with null structured lookups
  - capture understanding degrades to explicit no-capture mode
- the ordinary read path no longer performs the duplicate fallback `infer_query_understanding(...)` call inside `executive_retrieval.py`
- live target reproduction on `/home/lauratom/Asztal/ai/veglegeshermes-source`:
  - plugin files synced
  - container rebuilt
  - runtime after rebuild: `healthy`
  - Discord connected
- ad hoc live-target behavior probe showed:
  - first failure -> `transient_failure`
  - second failure -> `circuit_open`
- targeted regression ring stayed green:
  - `265 passed in 6.61s`
- accepted residual:
  - `control_plane` still performs one structured query-understanding call for ordinary packet analysis
  - therefore the blast radius is reduced, not eliminated
  - no manual Discord round-trip UAT was performed inside the Phase 61.1 closeout

## Phase 62 Planned Focus

- new critical Brainstack-owned finding:
  - the live system still cannot answer "is heartbeat / pulse / evolver actually live now?" from authoritative Brainstack state
- what the evidence says:
  - the deployed communication contract still exists in canonical `USER.md`
  - the live cron store can be empty while the assistant still talks as if prior autonomous systems are active
  - the live Brainstack DB contains heartbeat/evolver/pulse material mainly in transcript/continuity/profile lanes
  - current evidence does not yet show a clean authoritative operating-truth lane for current autonomous-system state
- accepted root-cause model for Phase 62 planning:
  - the primary Brainstack defect is not "forgot everything"
  - the deeper defect is that Brainstack preserves old narration better than current live-system authority
  - therefore ordinary questions about running mechanisms are vulnerable to stale residue and weak authority
- second new finding, recorded as a bounded boundary investigation:
  - cron session `session_cron_d0c8894058fb_20260423_170000.json` claimed it had no filesystem-write tools for `~/brainstack/pulse_test.log`
  - that session made no tool call at all before issuing the claim
  - current scheduler construction disables:
    - `cronjob`
    - `messaging`
    - `clarify`
    - `hermes-discord`
  - current evidence does not prove that terminal/file-write tooling was truly unavailable
- validated adjacent runtime findings:
  - cron sessions are fresh per-run sessions and explicitly use `skip_memory=True`
  - `/opt/data/home/tools/tomij/brainstack_pulse.py` currently only reads markdown tasks, prints markers, and appends to `pulse_log.txt`
  - `/opt/data/home/tools/tomij/native_moa_research.py` fails to import `hermes_tools` in direct container execution and therefore is not cleanly standalone-autonomous
  - Evolver CLI exists under `/opt/data/home/brainstack/evolver`, but no active loop process is running
  - `pip` is absent, but `uv` exists, so the stronger "dependencies cannot be installed at all" claim is not yet supported
- rejected overstatement from external audit:
  - current evidence does not support a universal claim that cron jobs never persist
  - current `jobs.json` contains the `Brainstack Pulse Test` job and historical cron output directories exist, including `f0e34b7d8d67`
- Phase 62 therefore exists to fix:
  - authoritative Brainstack live-system state recall
  - transcript-residue demotion for current-state questions
  - evidence-backed cron capability-truth classification

## Phase 62 Execution Outcome

- source-of-truth changes landed in:
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/live_system_state.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/operating_truth.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/operating_context.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/db.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/__init__.py`
- Brainstack now projects current Hermes scheduler state as typed operating truth:
  - `live_system_state`
- current-state authority now enters:
  - `list_operating_records(...)`
  - `search_operating_records(...)`
  - `Operating Context` system-prompt projection
- explicit absence is now representable:
  - `No Hermes scheduler jobs are currently present in live runtime state.`
- the operating-context section now states the authority rule explicitly:
  - only the listed live runtime state is authoritative for currently active autonomous mechanisms
- no new host seam was required for the Brainstack correction
- live proof on `/home/lauratom/Asztal/ai/veglegeshermes-source`:
  - `Brainstack Pulse Test` appears as a `live_system_state` row
  - the operating-context snapshot includes that row
  - a temp empty `jobs.json` produces the explicit absence row
  - final rebuilt container is `running healthy 0`
  - healthcheck: `running; connected=discord`
- focused regression ring after final carry-forward:
  - `265 passed in 6.62s`
- explicit boundary verdict:
  - the cron file-write incident remains classified as `false capability claim without tool attempt`
  - not as a Brainstack host-seam win

## Phase 63 Planned Focus

- remaining critical Brainstack-owned residual after Phase `62`:
  - ordinary task/operating kernel authority still depends too much on remote `structured_understanding`
- what the evidence now says:
  - Phase `61.1` contained the blast radius of remote-understanding failures, but did not remove the dependence itself
  - the accepted `61.1` residual remained:
    - `control_plane` still performs one structured query-understanding call for ordinary packet analysis
  - Phase `62` fixed authoritative current scheduler-state projection through `live_system_state`
  - Phase `62` did not solve ordinary task/operating route determination or capture eligibility
- accepted root-cause model for Phase `63` planning:
  - the deep defect is not merely "remote seam sometimes times out"
  - the deep defect is that the ordinary Brainstack kernel still places route/capture authority on a remote semantic-understanding seam where it should rely on local typed authoritative substrates
  - this cannot be corrected by rollback, timeout tuning, or heuristic restoration
- explicit constraints carried forward into Phase `63`:
  - no rollback to `v1.0.16`
  - no code-level heuristic routing revival
  - no hidden host-side classifier as a substitute
  - preserve the multimodal requirement in the new kernel shape
- Phase `63` therefore exists to define:
  - the local typed substrate for ordinary task/operating understanding
  - the cutover that removes mandatory remote-understanding hot-path authority
  - the bounded role, if any, for remaining off-path model-based understanding

## Phase 63 Execution Outcome

- source-of-truth changes landed in:
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/local_typed_understanding.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/db.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/task_memory.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/operating_truth.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/control_plane.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/executive_retrieval.py`
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/brainstack/__init__.py`
- the hot-path cutover is now explicit:
  - ordinary task/operating read analysis uses local typed-understanding only
  - the config-backed remote route resolver is no longer passed into ordinary packet building
  - absent explicit typed route payload, ordinary routing stays `fact_default`
- ordinary task/operating capture is now schema-driven:
  - structured JSON-like envelopes can commit task/operating records
  - plain natural-language turns no longer invoke semantic hot-path capture
- local typed read authority now uses:
  - explicit typed envelopes when present
  - `search_task_items(...)` for task recall
  - `search_operating_records(...)` plus bounded local current-record ranking fallback for operating recall
- task/operating commits now persist bounded `input_excerpt` metadata to strengthen later local retrieval without cue routing
- proof on source-of-truth temp harness:
  - `task_probe_found = true`
  - `operating_probe_found = true`
  - `packet_route.source = fact_default`
  - `packet_route.resolution_status = skipped`
  - explicit structured capture succeeds
  - ordinary natural-language capture returns `null`
- live target carry-forward on `/home/lauratom/Asztal/ai/veglegeshermes-source`:
  - container rebuilt successfully
  - container health `healthy`
  - restart count `0`
  - container probe showed:
    - `task_probe_found = true`
    - `operating_probe_found = true`
    - `packet_task_rows = 1`
    - `packet_operating_rows = 2`
    - `packet_route.source = fact_default`
    - `resolution_status = skipped`
    - no parser warning noise remained after the final parser guard fix
- focused regression ring after the final rebuild:
  - `265 passed, 8 warnings in 7.58s`
- accepted residual:
  - remote `structured_understanding.py` still exists in the codebase as a non-hot-path seam
  - broader multimodal explicit envelope design is still future work if more than JSON-like typed envelopes become necessary

## Phase 64 Completed

- runtime session-start now consumes explicit typed inbox envelopes and mirrors them into Brainstack
- first-turn context now includes canonical policy, runtime approval policy, live system state, and pending handoff tasks with exact `task_id` values
- `runtime_handoff_update` now provides explicit task lifecycle writeback through the Brainstack provider:
  - auto-approved terminal tasks move from `inbox` to `outbox`
  - approval-required tasks are blocked without explicit `approved_by`
  - completed terminal tasks are stored as typed state but no longer appear in the active pending snapshot
- paired live stabilizations landed:
  - Tier-2 request shape no longer sends invalid `response_format`
  - startup compression is bounded and pinned to the main Kimi path
  - `web_tools` metadata import no longer loads credential pools during tool discovery
- verification:
  - runtime handoff targeted suite: `5 passed`
  - broader regression ring: `324 passed`
  - cached Docker rebuild and recreate completed
  - live container: `healthy`, restart count `0`
  - container writeback probes passed for both auto-approved completion and approval-required blocking
- remaining boundary:
  - this is not a hidden autonomous executor loop
  - Brainstack remains memory/state/policy authority, not scheduler, executor, or governor

## Phase 31 Verify Findings

- the accepted root-cause model is now frozen as:
  - primary cause 1:
    - a partial `tier2_llm` behavior-contract revision became the active authority
  - primary cause 2:
    - explicit multi-message rule teaching did not converge into one committed canonical revision
  - primary cause 3:
    - Brainstack-only tool blocking was applied only on part of the live tool-execution surface
  - supporting symptom:
    - `session_search` remained available as a personal-memory fallback for full rule recall
  - non-cause:
    - the resolved provider-auth incident does not explain the later Brainstack degradation after auth recovered
- this closes `31` as a forensics phase and narrows `32` to a concrete hotfix surface instead of a vague behavior-memory rewrite
