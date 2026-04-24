# Roadmap

## Project Guardrails

Canonical immutable source:
- [IMMUTABLE-PRINCIPLES.md](./IMMUTABLE-PRINCIPLES.md)

Planning rule:
- roadmap and phase plans may not rewrite the top-level project principles
- if a phase seems to conflict with the immutable principles, the phase is wrong and must be replanned
- every Brainstack phase context or plan must explicitly check the GSD Planning Enforcement section in `IMMUTABLE-PRINCIPLES.md`

### Planning Rule

- when phase-level benchmark or oracle evidence conflicts with live deployed behavior, live deployed behavior has priority for the next planning decision
- broader capability expansion should not outrank deployability, upstream updateability, or real conversational quality without explicit evidence

## Completed Milestones

- `v2.0 Hermes Brainstack` — complete on 2026-04-10. Archive: `.planning/milestones/v2.0-ROADMAP.md`

## v2.0.1 Brainstack Integration Kit Stabilization

This stabilization detour makes Brainstack installable and re-installable into a fresh upstream Hermes checkout before the v2.1 profile-intelligence work continues.

### Phase 10.1. Brainstack Integration Kit And Upstream Hermes Update Workflow (INSERTED)
Wave:
- Upstream Update Stabilization

Depends on:
- Phase 10

Purpose:
- make Brainstack installable into a newly pulled/cloned upstream Hermes checkout without manual file copying
- preserve native Hermes-provider integration while keeping the update workflow repeatable
- add fail-closed compatibility checks so upstream Hermes changes do not silently create a half-wired memory runtime

Exit gate:
- a Brainstack-owned install/update command can copy the plugin payload into a target Hermes checkout
- doctor checks prove Brainstack is present, enabled, native memory is off, and the Docker/Discord runtime points at the intended gateway path
- the workflow fails closed when required Hermes lifecycle/provider surfaces are missing or incompatible

Recommended next step if gate passes:
- Phase 10.2

Recommended agent effort:
- high

## v2.1 Brainstack Extraction Intelligence

This milestone hardens the Brainstack ingest path from raw conversation into durable continuity, profile, and graph writes without drifting into language-specific regex sprawl.

### Phase 10.2. Tier-0 Noise Filtering And Ingest Hygiene (INSERTED)
Wave:
- Ingest Hygiene Stabilization

Depends on:
- Phase 10.1

Purpose:
- stop live durable-write noise before smarter extraction is added on top
- add language-neutral Tier-0 input hygiene so markdown tables, quoted transcripts, code blocks, pasted agent analyses, and document blobs do not land in durable profile memory
- prove the current Discord/Bestie runtime no longer keeps bleeding obvious junk into Brainstack shelves

Exit gate:
- pasted technical blobs and mixed quoted transcripts are filtered out of durable profile writes
- the current Brainstack path still preserves legitimate raw continuity/transcript evidence after filtering
- live verification shows the bleed is stopped even though Tier-2 inference is not added yet

Recommended next step if gate passes:
- Phase 11

Recommended agent effort:
- high

### Phase 11. Extraction Pipeline Foundation
Wave:
- Extraction Intelligence Foundation

Depends on:
- Phase 10.2

Purpose:
- extract the current ad hoc provider write path into an explicit Brainstack-owned ingest pipeline
- define the Tier-0 hygiene slot, Tier-1 bootstrap extractor slot, Tier-2 inference slot, and write-policy slot
- preserve the single Brainstack provider contract while making later smarter extraction modular and updatable

Exit gate:
- the ingest path is physically separated from ad hoc provider logic
- Tier-0, Tier-1, Tier-2, and write-policy seams are explicit
- anti-half-wire tests prove Hermes still uses the intended single Brainstack path

Recommended next step if gate passes:
- Phase 12

Recommended agent effort:
- high

### Phase 12. Tier-2 Multilingual Extractor And Reconciler
Wave:
- Extraction Intelligence Core

Depends on:
- Phase 11

Purpose:
- add a bounded Brainstack-owned Tier-2 extractor plus reconciler behind the new seam
- populate profile, graph, and higher-quality continuity summaries from natural conversation without relying on language-specific regex growth
- keep inference cost-bounded and deterministic at the write-policy boundary

Exit gate:
- implicit preferences, entities, relations, and decisions can be inferred through a dedicated Tier-2 path
- the reconciler can add, update, skip, or surface conflicts without becoming a second uncontrolled reasoning engine
- host/provider ownership remains unchanged

Recommended next step if gate passes:
- Phase 13

Recommended agent effort:
- high

### Phase 13. Safety, Temporal Supersession, And Recall Policy
Wave:
- Extraction Intelligence Safety

Depends on:
- Phase 11
- Phase 12

Purpose:
- prevent false durable writes from low-confidence inference
- preserve old and new states with explicit temporal supersession instead of destructive overwrite
- make recalled basis more visible when stakes or uncertainty require it

Exit gate:
- low-confidence durable writes are bounded or blocked
- corrections and changed states supersede cleanly without destructive erase
- recall policy stays token-disciplined and provenance-aware

Recommended next step if gate passes:
- Phase 14

Recommended agent effort:
- veryhigh

### Phase 14. Everyday Memory Recall Proving
Wave:
- Extraction Intelligence Proof

Depends on:
- Phase 12
- Phase 13

Purpose:
- prove that the smarter Brainstack path materially improves everyday continuity, preference-aware behavior, and relationship recall
- verify that the new pipeline remains practical instead of becoming another fake-smart layer

Exit gate:
- realistic continuity/preference/relationship scenarios improve meaningfully
- correction and supersession behavior are believable in practice
- the phase states clearly what is still not proven

Recommended next step if gate passes:
- Phase 14.1

Recommended agent effort:
- high

### Phase 14.1. Graph-Backed Wiring Audit And Anti-Half-Wire Gate (INSERTED)
Wave:
- Integration Audit

Depends on:
- Phase 14

Purpose:
- run a bounded late-stage anti-half-wire audit once the feature path is already implemented and smoke-proven
- use graph-backed evidence plus a small number of targeted tests and live-path checks to catch the classic agentic-coding failure patterns
- verify that the intended Brainstack wiring is still the real wiring, not just a paper architecture

Exit gate:
- no stale direct path or dead seam remains in the intended ingest/retrieval flow
- the audit is bounded and practical, not an oversized verification project
- the phase states clearly which proof came from graph evidence, which from tests, and which from live runtime checks

Recommended next step if gate passes:
- Phase 14.2

Recommended agent effort:
- high

### Phase 14.2. Preference application and skill boundary hardening (INSERTED)
Wave:
- Runtime Correctness
- Memory Ownership Boundaries

Depends on:
- Phase 14
- Phase 14.2
- Phase 14.1

Purpose:
- make fresh user communication preferences apply quickly and reliably in the live runtime instead of only showing up later in Tier-2 durability
- preserve Hermes skill learning, but stop user identity, style, and preference facts from leaking into procedural skill memory paths
- tighten Brainstack-only memory ownership so personal profile facts go only through Brainstack shelves while reusable procedures may still use `skill_manage`
- normalize duplicated user identity and preference records so the runtime does not drift into parallel truths like `User` vs `Tomi`

Exit gate:
- live follow-up messages stop repeating freshly-forbidden style behavior like emoji spam, overfriendly framing, or em-dash usage after the user corrects them
- Brainstack-only mode no longer routes user-profile or communication-preference memory through `skill_manage`
- procedural skill learning remains available for real reusable workflows and is not globally amputated
- identity, preference, and relation storage is materially cleaner after normalization/deduping than it was in the failing live smoke

Recommended next step if gate passes:
- Phase 15

Recommended agent effort:
- high

Plans:
- [ ] TBD (run /gsd-plan-phase 14.2 to break down)

### Phase 15. Adaptive Memory Usefulness Scoring And Retrieval Telemetry
Wave:
- Adaptive Recall Optimization

Depends on:
- Phase 14

Purpose:
- add adaptive usefulness telemetry so Brainstack can learn which recalled items are repeatedly useful or repeatedly low-value
- improve retrieval prioritization and token discipline without replacing the existing extraction, safety, and recall architecture
- prepare a Brainstack-shaped scoring model that is richer than a flat retrieval/usefulness ratio and can later use shelf-aware and provenance-aware signals

Exit gate:
- Brainstack can record bounded usefulness telemetry for recalled items without corrupting the single-provider architecture
- adaptive scoring or equivalent prioritization can be enabled without bypassing Phase 13 safety/provenance work
- the design clearly states what came from donor inspiration versus what was reshaped to fit Brainstack

Recommended next step if gate passes:
- Phase 16

Recommended agent effort:
- high

### Phase 15.1. Host Memory Ownership And Personal-Preference Tool Boundary Hardening (INSERTED)
Wave:
- Runtime Ownership Corrections
- Host Guidance Hardening

Depends on:
- Phase 14.2
- Phase 15

Purpose:
- close the remaining host-side ownership leaks where personal profile/style memory can still spill into generic skill, note, or file workflows
- tighten Brainstack-only runtime guidance so personal preference capture routes into Brainstack memory instead of `skill_view`, `skill_manage`, `read_file`, or `write_file`
- keep procedural skills alive while making personal-memory ownership unambiguous
- remove the mismatch between stored preference facts and the tool behaviors the model is still being nudged toward

Exit gate:
- live preference/style capture no longer reaches for generic note files or skill inspection/writes in Brainstack-only mode
- Brainstack-only host guidance no longer broadly nudges personal-memory capture toward legacy memory/skill/file habits
- procedural workflow skill usage still works when the task is actually procedural
- live Discord smoke proves the model applies personal style rules without narrating memory internals, notes-file writes, or skill detours

Recommended next step if gate passes:
- Phase 16

Recommended agent effort:
- high

### Phase 16. Layer-2 graph enrichment and implicit relation discovery
Wave:
- Knowledge Graph Deepening
- L2 Architecture Review

Depends on:
- Phase 15.1
- Phase 15
- Phase 13
- Phase 12

Purpose:
- re-evaluate the current Layer 2 behavior end-to-end because the current graph is still too weak for the intended product
- deepen Brainstack's own graph so it can represent richer knowledge connections, not only explicit state and relation statements that were directly said in text
- design a bounded, Brainstack-owned implicit relation discovery path above `graph_entities`, `graph_relations`, and `graph_states`
- keep the solution compatible with the current single-provider architecture, token-discipline goals, and update-safe modularity rules
- review external inspiration such as `https://github.com/itsXactlY/neural-memory`, but only as a donor idea source, not as an architecture transplant

Exit gate:
- Phase 16 produces a clear Brainstack-specific L2 target design for a much stronger knowledge graph
- the plan distinguishes explicit graph truth, inferred/implicit links, confidence, temporal behavior, and recall policy cleanly
- the design stays bounded and does not introduce a second memory runtime, separate graph owner, or uncontrolled token blow-up
- external donor repos are documented as inspiration only, with explicit reasons for what is rejected versus adapted

Recommended next step if gate passes:
- Phase 16.1

Recommended agent effort:
- xhigh

### Phase 16.1. Donor Re-centering Audit And Recovery Scope (INSERTED)
Wave:
- Strategy Reset
- Donor Truth Audit

Depends on:
- Phase 16

Purpose:
- stop further feature drift and re-evaluate whether Brainstack still reflects the original donor-first design
- produce an honest donor-by-donor audit of what was actually adopted from Hindsight, Graphiti, and MemPalace versus what was replaced by Brainstack-owned glue
- identify where the current system is strong because of integration hardening versus where it is weak because donor power was diluted
- define a recovery scope that restores donor strengths without throwing away the valuable single-owner, installer, doctor, and safety work

Hard rules:
- this phase must treat the current `3/15` LongMemEval baseline as mandatory evidence, not as an optional anecdote
- this phase must classify every major weakness as either:
  - donor-strength missing/diluted
  - justified Brainstack-owned integration
  - accidental custom glue
- this phase must not allow new feature work to slip in under the label of “recovery”
- this phase must not solve donor-strength gaps with new Brainstack heuristics
- this phase must produce a donor-first target shape for later restoration phases, not an MVP compromise

Exit gate:
- there is an explicit table for each core donor:
  - original intended strength
  - what is actually present now
  - what remains worth keeping local
  - what should be thinned or handed back to donor-shaped logic
- the project has a written feature freeze rule for this recovery window
- the roadmap clearly distinguishes integration value from memory-kernel value
- the output is strong enough to drive `16.2/17/18/19` as hard-rule phases instead of loose cleanup ideas

Recommended next step if gate passes:
- Phase 16.2

Recommended agent effort:
- xhigh

### Phase 16.2. Modularization Recovery And Glue Reduction Plan (INSERTED)
Wave:
- Architecture Cleanup
- Boundary Recovery

Depends on:
- Phase 16.1

Purpose:
- reduce unnecessary Brainstack-owned middle logic so the project does not keep drifting away from the donor-first architecture
- identify which modules are legitimately Brainstack-owned:
  - ownership
  - orchestration
  - safety
  - packaging
  - host integration
- identify which modules became accidental custom kernel logic and should be thinned, replaced, or re-centered around donor strengths

Hard rules:
- this phase must produce a concrete module-by-module recovery contract, not a qualitative “cleanup later” note
- any module that behaves like donor-strength replacement must be presumed guilty until justified otherwise
- the recovery plan must prefer deleting or thinning glue over adding new abstraction layers
- no “temporary MVP fix” may be used as the end state for `17/18/19`
- every retained Brainstack-owned module must defend its existence as one of:
  - ownership
  - orchestration
  - safety
  - packaging
  - host integration

Exit gate:
- there is a concrete modularization recovery plan, not just a complaint list
- each major module is classified as:
  - keep local
  - thin down
  - donor-recenter
  - remove
- the recovery plan reduces custom glue instead of adding another layer of indirection
- `17/18/19` each inherit explicit non-MVP, donor-first recovery contracts from this phase

Recommended next step if gate passes:
- Phase 17

Recommended agent effort:
- xhigh

### Phase 17. Layer-1 Continuity And Smartening Restoration
Wave:
- L1 Recovery
- Hindsight Re-centering

Depends on:
- Phase 16.2

Purpose:
- restore the original reason Hindsight was chosen for Layer 1: the agent should feel noticeably smarter, not merely preserve raw turns
- strengthen continuity, retention, and follow-up intelligence without regressing into heuristic preference sprawl
- make L1 feel more like true continuity/smartening again and less like a bounded transcript plus local glue
- make donor-first hybrid retrieval the primary L1 path instead of keeping the old heuristic Tier-1 path in the center
- restore Hindsight/TEMPR-style executive fusion behavior over donor-backed graph and corpus retrieval channels rather than inventing another Brainstack-local retrieval engine

Hard rules:
- this phase must not grow regex or keyword heuristics as the main answer
- this phase must restore donor-shaped smartening strength, not only repackage existing Brainstack shelves
- this phase must target “noticeably smarter agent” behavior as a required outcome, not a nice-to-have
- this phase must not settle for a merely serviceable L1 if the result still feels like local glue over transcript recall
- this phase must not use temporary legacy aligners or heuristic bridge logic as the accepted end state
- donor-restored L1 behavior must become the primary path, not a sidecar around the old path
- this phase must use donor-aligned hybrid retrieval as the primary L1 path:
  - vector similarity
  - FTS / keyword search
  - temporal signal
- this phase must treat L1 as executive retrieval intelligence, not as another storage shelf
- this phase must not assume SQLite remains the engine for all memory intelligence
- this phase must treat handwritten language-specific trigger lists and regex extraction growth as fatal architectural drift, not as an acceptable multilingual compromise
- benchmark improvement may confirm success, but may not replace the requirement that the agent actually feels smarter in real follow-up behavior

Exit gate:
- L1 clearly improves cross-session continuity and follow-up intelligence
- the design remains language-agnostic and avoids new regex-heavy logic
- Brainstack still owns the host boundary, but Hindsight-shaped strengths are more visible again
- the result is judged against the original Hindsight reason-for-choice, not against a weaker MVP threshold
- Phase `17` also defines and proves a faster eval ladder:
  - fast Brainstack-adapted acceptance scenarios
  - a mini smartening suite
  - a small LongMemEval subset
  - final boss LongMemEval only at the restoration gate

Recommended next step if gate passes:
- Phase 18

Recommended agent effort:
- xhigh

### Phase 18. Layer-2 Knowledge Graph Restoration
Wave:
- L2 Recovery
- Graphiti Re-centering

Depends on:
- Phase 17
- Phase 16.2

Purpose:
- continue beyond the bounded Phase 16 graph improvement and restore the original Graphiti-level ambition
- strengthen relationship discovery, temporal truth handling, and graph retrieval so L2 becomes a genuinely strong knowledge graph rather than only a safe local approximation
- keep explicit truth primary while making the graph materially more useful in live recall
- restore Graphiti-level graph usefulness on an embedded graph backend, with Kuzu as the default target unless implementation evidence disproves it

Hard rules:
- this phase must target a genuinely strong knowledge graph, not only a safer or tidier one
- explicit truth must remain primary, but inferred and historical graph behavior must become materially useful rather than nominal
- this phase must not stop at packaging improvements if graph usefulness is still weak
- this phase must not solve graph weakness by adding shallow local hacks where donor-shaped graph behavior should exist
- this phase must not default back to SQLite-only graph behavior if that blocks donor-strength traversal and retrieval

Exit gate:
- L2 is stronger in real knowledge-graph behavior, not just safer in packaging
- explicit truth, historical truth, conflict, and inferred links remain clearly separated
- relationship reasoning is materially more useful in real conversations
- the result is strong enough that calling L2 “Graphiti-recentered” is defensible, not aspirational

Recommended next step if gate passes:
- Phase 19

Recommended agent effort:
- xhigh

### Phase 19. Layer-3 Corpus And Packing Restoration
Wave:
- L3 Recovery
- MemPalace Re-centering

Depends on:
- Phase 18
- Phase 16.2

Purpose:
- restore the original reason MemPalace was chosen: strong long-horizon corpus handling and high-quality bounded packing
- strengthen corpus ingestion, retrieval, and packing so large-document memory becomes a real competitive strength instead of a mostly nominal shelf
- improve real corpus usefulness without sliding into benchmark-only tuning
- restore MemPalace-style raw corpus retrieval as the primary L3 strength, with an embedded Chroma-style backend as the default target

Hard rules:
- this phase must make L3 a real strength, not a checkbox shelf
- token savings here must come from better corpus retrieval and packing quality, not from extra hacks layered on top
- this phase must not accept “it stores documents” as success if long-horizon recall is still weak
- this phase must restore donor-shaped corpus power without turning Brainstack into a separate document platform
- this phase must not treat compression-first design as the main target if raw corpus retrieval remains stronger

Exit gate:
- L3 demonstrates materially stronger long-document/corpus recall and packing quality
- token discipline improves through better corpus handling rather than through more hacks
- the resulting corpus path still fits the single-provider architecture
- the result is good enough to claim MemPalace-style restoration in substance, not only in naming

Recommended next step if gate passes:
- Phase 20

Recommended agent effort:
- xhigh

### Phase 20. Real-World Proof And Restoration Verdict
Wave:
- End-to-End Proof
- Recovery Verdict

Depends on:
- Phase 19

Purpose:
- prove in real usage that the recovered Brainstack is not just more elaborate, but actually closer to the original best-of-three goal
- decide honestly whether the donor-first vision was actually restored in practice

Hard rules:
- this phase must deliver a hard verdict, not a vague “better than before” conclusion
- if the donor-first vision is still not restored, the phase must say so explicitly
- this phase must judge the system against the original “big 3 plus thin glue” ambition, not against the weaker current-state baseline
- this phase must not close the milestone on aesthetics, code volume, or architectural storytelling alone

Exit gate:
- real-world use shows the recovered stack feels stronger, not merely more complex
- the project has an explicit verdict on whether the donor-first vision was successfully restored
- the verdict is based on substance and hard evidence, not on soft interpretation or MVP-level acceptance

Recommended next step if gate passes:
- milestone closeout or next milestone planning

Recommended agent effort:
- xhigh

### Phase 20.1. Benchmark-Exposed Memory Fidelity Recovery (INSERTED)
Wave:
- Corrective Recovery
- Fidelity Gap Closure

Depends on:
- Phase 20

Purpose:
- close the benchmark-exposed gap that remained after the donor-first recovery track
- improve temporal ordering, multi-session aggregation, exact detail carry-through, and irrelevant recall suppression without falling back into benchmark-gaming or heuristic drift
- preserve the recovered donor-first architecture while making the final proof verdict rerunnable with a materially stronger end-to-end result
- restore semantic retrieval on actual conversation history rather than only on corpus documents
- make temporal evidence explicitly readable in the rendered prompt
- stop legacy graph-ingress junk from polluting truth context
- widen transcript evidence enough that raw exact-detail turns can actually surface
- replace shallow flat clipping with adaptive evidence packing that preserves answer-bearing detail
- clarify prompt-side evidence priority for specific non-conflicted recalled facts without adding blind memory bias

Hard rules:
- this phase must not solve the gap with benchmark-specific prompt tricks or handwritten multilingual heuristics
- this phase must not undo the recovered `L1` / `L2` / `L3` architecture
- this phase must treat the unchanged `3 / 15` final-boss result as blocking evidence, not as background noise
- this phase must improve substantive memory fidelity, not just benchmark cosmetics
- this phase must treat conversation-history semantic indexing as a first-class requirement, not as optional polish
- this phase must not leave the legacy graph ingress free to turn arbitrary user phrases into truth rows
- this phase must improve exact-detail carry-through, not just retrieval breadth
- this phase must not solve model-overrides with a blind “always trust memory” prompt hack

Exit gate:
- final-boss benchmark evidence is materially stronger than the flat Phase `20` result
- temporal ordering, multi-session aggregation, and exact-detail recall are measurably improved
- irrelevant graph/corpus contamination in recalled context is reduced without amputating useful recall
- the system is ready to rerun Phase `20` for a fresh restoration verdict
- continuity / transcript evidence is semantically searchable through the donor-aligned retrieval path
- retrieved conversational evidence carries explicit enough temporal labels for ordering questions
- transcript evidence is broad enough to surface raw answer-bearing detail when summaries are lossy
- adaptive packing preserves answer-bearing details better than the old flat `220`-character trimming path
- the prompt contract makes specific non-conflicted recalled facts outrank generic prior knowledge

Recommended next step if gate passes:
- rerun Phase 20 verdict

Recommended agent effort:
- xhigh

### Phase 20.2. High-Precision Conversational Fact Retrieval Recovery (COMPLETE / FORENSICS CLOSED)
Wave:
- Retrieval Precision Recovery
- Residual Error Closure

Depends on:
- Phase 20.1

Purpose:
- close the residual exact-fact error class that remained after the `9 / 15` post-`20.1` final-boss rerun
- improve multi-entity conversational retrieval, answer-bearing turn selection, and update-priority without reopening the restored donor-first architecture
- separate true query-decomposition work from single-topic fact-seeking ranking work so the next corrective phase does not collapse into one vague lever
- preserve the distinction between immediate regression forensics and the longer-term retrieval architecture needed for stable high benchmark performance

Hard rules:
- this phase must treat the remaining problem as a targeted conversational fact-retrieval issue, not as a broad architecture rollback
- this phase must not assume query decomposition alone fixes every remaining fail
- this phase must distinguish:
  - multi-entity decomposition
  - fact-seeking ranking
  - packing fidelity
  - user-turn priority
  - exact-value supersession
- this phase must not fall back into multilingual regex sprawl or benchmark-specific hacks
- if decomposition is implemented, it must use a single bounded auxiliary step rather than a separate classify-then-decompose LLM chain
- this phase must preserve the recovered donor-first shell plus `L1/L2/L3` structure
- this phase must not confuse:
  - immediate split-pass regression isolation
  - with the later architectural move toward query-intent-aware retrieval modes

Current recorded status:
- the first `20.2` execute bundle improved some exact-fact cases but regressed the final-boss rerun from `9 / 15` to `7 / 15`
- bounded query decomposition is the leading suspect, but not yet the only proven cause
- the next required move is a pure A/B rerun with `query_decomposer=None`, leaving every other `20.2` lever unchanged
- only if that does not recover the score should priority-bonus ablation start
- within those bonuses, `digit` / quote bonuses are the first ablation targets; `user-led` priority is a softer candidate because it still has an everyday epistemic basis
- measured dataset mix now shows large temporal and multi-session pressure:
  - `26.6%` temporal-reasoning
  - `26.6%` multi-session
  - `15.6%` knowledge-update
- this supports a later architecture direction where executive retrieval routes among:
  - relevance retrieval
  - exhaustive/aggregate recall
  - timestamp-ordered retrieval
- that later routing should be fail-open rather than a hard exclusive classifier, so wrong intent guesses do not zero out the generic relevance fallback
- the current shell-side exact-value auto-supersession should be treated as temporary tech debt until a later Tier-2 / reconciler path can carry explicit update intent without donor-boundary drift
- the first pure A/B rerun with `query_decomposer=None` has now been executed and improved the score to `10 / 15`
- that rerun recovered three decomposition-era regressions:
  - `6c49646a`
  - `d682f1a2`
  - `gpt4_7f6b06db`
- decomposition is therefore no longer just a suspect; it is the primary proven regression lever in the initial `20.2` bundle
- the next required move after this proof was a bonus/ranking A/B pass; that pass has now shown that removing `digit` + quote together collapses the score to `3 / 15`
- therefore the next required move is no longer “remove both suspicious bonuses”
- it is:
  - keep decomposition disabled
  - test quote-off alone
  - test digit-off alone
  - only then revisit `user-led`
- the stronger `authoritative` grounding wording is now recorded as a plausible coupling factor, but not yet a proven primary cause; it needs its own future A/B if it becomes the next target
- the quote-off-only pass has now also been run and dropped the score to `5 / 15`
- therefore quote is also currently load-bearing, and the next required move narrows again:
  - restore the `10 / 15` decomposition-off baseline
  - test `digit`-off only
  - only after that consider any grounding-only A/B
- the `digit`-off-only pass has now also been run and dropped the score to `7 / 15`
- therefore the bonus-forensics matrix is now closed, and the best current baseline remains:
  - decomposition off
  - quote on
  - `digit` on
  - `user-led` on
  - `10 / 15`
- the wording-only grounding A/B has now also been run and dropped the score to `6 / 15`
- therefore the low-cost local-forensics cycle is closed, and the best current baseline remains unchanged
- the forensic interpretation is now explicit:
  - the current local overlay stack is compensatory, not fundamentally strong
  - all local levers are load-bearing, yet the net gain over the post-`20.1` baseline is still only `+1`
  - this reinforces that the remaining gap is structural, not likely solvable by more overlay tuning
- the remaining gap should now be treated as primarily structural:
  - temporal / time-difference retrieval
  - aggregate / exhaustive recall
  - multi-event ordering beyond single-query top-K
- the next structural retrieval design must not inherit the current decomposition gate/path as-is
- future intent-aware routing should start clean:
  - temporal -> timestamp-ordered path
  - aggregate -> exhaustive / widened recall path
  - simple fact -> relevance retrieval without the current decomposition logic
  - decomposition only if a later design reintroduces it as a narrowly justified multi-entity helper

Exit gate:
- residual final-boss misses are reduced through exact-fact retrieval improvements rather than architecture churn
- multi-entity questions recover more than one sub-event reliably
- single-topic exact-value questions prefer result turns over setup turns
- newer corrected values outrank older ones more consistently
- the post-`20.2` split-pass reruns identify the actual regression lever before any new bundled tuning continues

Recommended next step:
- plan the new structural retrieval phase `20.3`

Recommended agent effort:
- xhigh

### Phase 20.3. Structural Retrieval Routing For Temporal, Aggregate, And Fail-Open Intent-Aware Queries (EXECUTE COMPLETE)
Wave:
- Retrieval Architecture
- Executive Routing

Depends on:
- Phase 20.2

Purpose:
- replace further local overlay-tuning as the main path forward with a clean structural retrieval phase
- introduce separate retrieval routes for:
  - straightforward fact lookup
  - temporal / time-difference questions
  - aggregate / exhaustive-recall questions
- preserve the donor-first shell while making `L1` executive retrieval fail-open and intent-aware instead of one universal ranking path

Hard rules:
- this phase must not inherit the current decomposition gate/path as-is
- this phase must not frame the next work as more `20.2` bonus / wording tuning
- simple fact retrieval must remain decomposition-free by default
- temporal questions must get a timestamp-ordered retrieval path
- aggregate questions must get a widened / exhaustive recall path
- any future decomposition may return only as a narrowly justified helper for true multi-entity queries
- routing must be fail-open:
  - a specialized path may bias retrieval
  - but generic relevance fallback must remain
- any future fail-open widening must remain explicitly bounded:
  - bounded transcript/continuity widening is acceptable
  - unbounded "dump more rows and hope" fallback is disallowed
- this phase must not grow more shell-side donor logic or multilingual regex drift
- benchmark evidence remains diagnostic, not the product goal; the target is a better everyday kernel

Current recorded rationale:
- the full `20.2` forensic cycle is closed
- the best current proven baseline is `10 / 15`
- the local overlay stack is compensatory rather than fundamentally strong
- the net gain over the post-`20.1` baseline is only `+1`
- therefore the remaining gap should now be treated as structural rather than as more local tuning debt
- `20.3` gained a second execute slice in `20.3-02-SUMMARY.md` that closed the two previously named pending gaps:
  - route-specific aggregate rendering / packing
  - proof separation between retrieval correctness and LLM answer correctness
- the bounded real-path rerun on the updated `20.3` stack then landed at:
  - raw answer score: `6 / 15`
  - retrieval-correct score: `3 / 15`
  - both retrieval-correct and answer-correct: `2 / 15`
- therefore `20.3` is now proven to have improved structural architecture and proof instrumentation, but not yet the live retrieval result enough for a restoration claim
- the bounded `20.3` forensic bundle has now completed:
  - legacy answer-only comparability on the current `20.3` stack: `3 / 15`
  - current split-proof rerun on the same stack: `5 / 15`
  - route metadata now shows `applied_mode=fact` in `15 / 15`
  - route metadata now shows `route_source=fallback` in `14 / 15`
  - the dominant fallback reason is route-hint `401` failure in the target runtime
  - backend population logging now shows `Kuzu` sparse and `Chroma` dense in this benchmark path
- therefore `20.4` planning is now evidence-gated open
- the main measured blockers are now:
  - live route-hint reliability in the target runtime
  - graph population / publication adequacy in the benchmark seeding path
  - judge / proof reliability where raw answer score still overstates real memory quality
- temporal / aggregate bonus-bypass is recorded as a code-level architectural concern, but not yet as a benchmark-causal verdict
- exact-value supersession remains open technical debt:
  - important
  - but not the immediate next `20.3` cut

Recommended next step if gate passes:
- `20.4` planning for bounded real-path retrieval forensics and proof reliability hardening

Recommended agent effort:
- xhigh

### Phase 20.4. Live Fact-Path Parity, Route-Hint Reliability, And Backend Population Forensics (EXECUTED)
Wave:
- Runtime Forensics
- Proof Hardening

Depends on:
- Phase 20.3

Purpose:
- explain why the current live fact-fallback path regressed far below the earlier `20.2` decomp-off baseline
- fix the measured live route-hint runtime failure
- audit why benchmark-path `Kuzu` publication/population is sparse while `Chroma` is dense
- harden proof/judge interpretation so future restoration claims are evidence-safe

Hard rules:
- the first explicit workstream must be fact-path parity, not route-hint or judge tuning
- this phase must not reopen `20.2` overlay tuning
- this phase must not treat route-hint `401` as an architecture verdict before runtime/configuration is traced
- this phase must not treat `Kuzu` sparsity as a full retrieval-quality verdict before publication/population audit is complete
- this phase must preserve the retrieval-vs-answer proof split
- this phase must end with comparable reruns in both legacy answer-only and split-proof modes
- benchmark evidence remains diagnostic, not the product goal; the target is a better everyday kernel

Current recorded rationale:
- `20.4` execute is now complete as a bounded live forensics phase
- fixed-clock answer-only comparability on the current live stack is `5 / 15`
- this improved the earlier `20.3` legacy comparability result of `3 / 15`
- therefore part of the old `10 / 15 -> 3 / 15` collapse was runtime/prompt instability
- but parity is still not restored versus the earlier `20.2` decomp-off `10 / 15`
- fixed-clock split-proof on the same live stack is:
  - raw answer score: `6 / 15`
  - `retrieval_correct`: `2 / 15`
  - `both_correct`: `2 / 15`
- direct route-resolver injection removed the earlier `401` route-hint failure
- however, route activation remained minimal:
  - `route_source=default`: `14 / 15`
  - `route_source=direct_benchmark_route_hint`: `1 / 15`
  - `requested_mode=fact`: `15 / 15`
  - `applied_mode=fact`: `15 / 15`
- backend population logging now distinguishes `SQLite` graph counts from `Kuzu`
- measured backend picture:
  - `Chroma` nonzero in `15 / 15`
  - `SQLite` graph entity count nonzero in `3 / 15`
  - `Kuzu` graph entity count nonzero in `3 / 15`
- therefore the graph problem is currently best described as sparse graph yield, not a proven `Kuzu`-only publication failure
- proof/judge hardening remains necessary:
  - suspicious answer-judge passes still exist
  - raw answer score still overstates reliable Brainstack-supplied evidence
  - post-run manual review now records that `retrieval_correct=2 / 15` is a judge-underestimate, with the strongest current false-negative rows at `6a1eabeb` and `e9327a54`
  - derived/integrated rows such as `9ee3ecd6`, `69fee5aa`, and `195a1a1b` remain outside clean retrieval success and should not be reclassified without a judge-definition change

Recommended next step:
- plan `20.5` from the finished `20.4` forensic findings

Recommended agent effort:
- xhigh

### Phase 20.5. Proof Calibration, Fact-Path Restoration, Route Activation, And Graph Yield Recovery (EXECUTED)
Wave:
- Restoration
- Proof Hardening

Depends on:
- Phase 20.4

Purpose:
- calibrate the retrieval judge before treating split-proof retrieval counts as architecture truth
- restore live fact-path parity toward the earlier stronger decomp-off baseline
- increase structural route activation coverage now that the `401` runtime failure is removed
- improve sparse graph yield in the benchmark path while preserving donor-first boundaries

Hard rules:
- the first explicit workstream must be retrieval-judge calibration
- this phase must not collapse back into `20.2` overlay tuning
- this phase must not silently promote derived/integrated evidence cases into retrieval success
- this phase must not reintroduce the old decomposition gate or multilingual keyword routing
- if route activation is widened, the phase must verify that newly activated routes do not silently lose the currently load-bearing priority behavior without an explicit replacement
- this phase must not treat raw answer score as the primary restoration truth metric
- this phase must end with comparable answer-only and split-proof reruns

Current recorded rationale:
- `20.4` proved that part of the old `10 / 15 -> 3 / 15` collapse was runtime/prompt instability, but parity still only recovered to `5 / 15`
- `20.5` parity restoration must first document the exact runtime environment of the earlier `20.2` decomp-off `10 / 15` run before comparing it to the current benchmark path
- `20.4` removed the live route-hint `401`, but the route gate still activated a non-default route in only `1 / 15`
- `20.4` showed that graph sparsity appears already at the `SQLite` layer, so the graph problem is sparse yield rather than a proven `Kuzu`-only publication failure
- `20.4` also showed that `retrieval_correct=2 / 15` is a judge-underestimate rather than a trustworthy planning-grade metric
- the strongest current retrieval-judge false negatives are `6a1eabeb` and `e9327a54`
- derived/integrated rows such as `9ee3ecd6`, `69fee5aa`, and `195a1a1b` remain outside clean retrieval success until the judge definition is changed explicitly
- `20.5` execute is now complete with a split outcome:
  - answer-only comparability: `4 / 15`
  - split-proof raw answer score: `6 / 15`
  - split-proof `retrieval_correct`: `5 / 15`
  - split-proof `both_correct`: `4 / 15`
- `20.5` therefore succeeded at proof calibration but failed at live restoration
  - route activation still stayed mostly dead:
    - `route_source=default`: `14 / 15`
    - `applied_mode=fact`: `14 / 15`
    - `applied_mode=aggregate`: `1 / 15`
  - graph yield stayed sparse:
    - `Chroma` nonzero: `15 / 15`
    - `SQLite` graph nonzero: `3 / 15`
    - `Kuzu` graph nonzero: `3 / 15`
  - calibrated retrieval now cleanly recovers at least the known false-negative cases `6a1eabeb` and `e9327a54`

Recommended next step:
- plan `20.6`

Recommended agent effort:
- xhigh

### Phase 20.6. Live Restoration For Fact Parity, Route/Graph Recovery, And Profile Retrieval (EXECUTED)
Wave:
- Restoration
- Retrieval Recovery

Depends on:
- Phase 20.5

Purpose:
- restore live fact-path parity against the earlier stronger decomp-off path
- recover route activation and graph yield together as one coupled restoration problem
- audit profile / identity retrieval misses as an explicit retrieval class
- audit bounded retrieval-correct / answer-wrong grounding leaks without reopening broad proof work

Hard rules:
- fact-path parity must be the first explicit workstream
- route activation and graph yield must be treated together, not as isolated sequential wins
- this phase must not collapse back into `20.2` overlay tuning
- this phase must not reintroduce the old decomposition gate or multilingual keyword routing
- profile / identity retrieval misses must be named explicitly, not hidden inside generic retrieval failure language
- bounded grounding leak audit must stay bounded to proven retrieval-correct / answer-wrong rows
- this phase must end with comparable answer-only and split reruns

Current recorded rationale:
- `20.6` repaired two real live blockers:
  - stale target-plugin `executive_retrieval.py`
  - MiniMax route-hint response-shape parsing with empty `content` and non-empty `reasoning_content`
- after those fixes, live structural routing actually activated:
  - answer-only `route_source=direct_benchmark_route_hint`: `13 / 15`
  - split `route_source=direct_benchmark_route_hint`: `12 / 15`
  - answer-only non-fact applied modes: `6 / 15`
  - split non-fact applied modes: `4 / 15`
- `20.6` also showed that backend population is no longer mostly empty:
  - answer-only:
    - `SQLite` graph nonzero: `14 / 15`
    - `Kuzu` graph nonzero: `14 / 15`
    - `Chroma` nonzero: `15 / 15`
  - split:
    - `SQLite` graph nonzero: `12 / 15`
    - `Kuzu` graph nonzero: `12 / 15`
    - `Chroma` nonzero: `15 / 15`
- despite those repairs, live restoration failed harder:
  - answer-only: `3 / 15`
  - split raw answer: `2 / 15`
  - split `retrieval_correct`: `2 / 15`
  - split `both_correct`: `1 / 15`
- this means the old dead-route state was hiding the true live failure shape rather than preserving a better system
- fact-path parity is now even further below the old `20.2` decomp-off `10 / 15` baseline
- `5d3d2817` remains a named live profile / identity retrieval miss class
- `d682f1a2` remains a named retrieval-correct / answer-wrong grounding leak class
- `6a1eabeb` and `gpt4_7f6b06db` now also define a separate execution-path anomaly class:
  - blank route metadata
  - missing `<memory-context>` block

Recommended next step:
- plan `20.7`

Recommended agent effort:
- xhigh

### Phase 20.7. Execution-Path Hardening, Fact Parity, And Route-Quality Recovery (EXECUTED)
Wave:
- Restoration
- Retrieval Recovery

Depends on:
- Phase 20.6

Purpose:
- fix the live execution-path anomaly before treating those rows as normal retrieval failures
- restore live fact-path parity against the older stronger decomp-off path
- recover route quality with explicit separation between route selection, candidate quality, and evidence packing
- recover the named profile / identity retrieval miss class
- re-check the bounded grounding leak class after the retrieval work

Hard rules:
- execution-path anomaly hardening must be the first explicit workstream
- fact-path parity must remain immediately after the anomaly work and must not slide back again
- route-quality work must explicitly separate:
  - selection
  - candidate quality
  - packing
- this phase must not reopen proof-calibration as its main mission
- this phase must not collapse back into `20.2` overlay tuning or decomposition revival
- profile / identity misses must stay named explicitly
- bounded grounding leak work must stay bounded to proven retrieval-correct / answer-wrong rows
- this phase must end with comparable answer-only and split reruns

Current recorded rationale:
- `20.7` fixed three real correctness defects before the comparable reruns:
  - timezone-naive / timezone-aware datetime mixing in temporal priority sorting
  - runner masking of missing `<memory-context>` by falling back to the whole prompt
  - ambiguous explanatory route-hint parsing silently turning into a fake route instead of explicit fallback
- targeted source validation passed:
  - `36 passed`
- the reproduced `6a1eabeb` path no longer shows the old execution anomaly:
  - memory block present
  - route metadata present
  - no blank `<memory-context>` path
- comparable `20.7` answer-only rerun:
  - `4 / 15`
  - suspicious answer-judge passes: `1`
  - `memory_context_present`: `15 / 15`
  - `route_source=fallback`: `15 / 15`
  - `applied_mode=fact`: `15 / 15`
  - `SQLite` graph nonzero: `12 / 15`
  - `Kuzu` graph nonzero: `12 / 15`
  - `Chroma` nonzero: `15 / 15`
- comparable `20.7` split rerun:
  - raw answer: `6 / 15`
  - `retrieval_correct`: `4 / 15`
  - `both_correct`: `3 / 15`
  - suspicious answer-judge passes: `1`
  - failure layers:
    - `retrieval`: `8`
    - `llm_answer`: `1`
    - `answer_recovered_despite_retrieval_gap`: `3`
    - `none`: `3`
  - `memory_context_present`: `15 / 15`
  - `route_source=fallback`: `15 / 15`
  - `applied_mode=fact`: `15 / 15`
- the `20.7` verdict is therefore:
  - execution-path anomaly hardening succeeded
  - live restoration still failed
  - the next blocker is no longer silent path loss
  - the next blocker is that live route-hint output is too ambiguous / unusable under the current strict parser, so the full comparable runs collapse back to fact-only fallback
  - fact-path parity remains badly unresolved versus the older `20.2` decomp-off `10 / 15` baseline
  - profile / identity retrieval and multi-session exact-fact retrieval remain weak even when memory is present
  - the agreed `20.8` planning guard is now explicit:
    - start with a raw-output route-hint audit rather than another blind prompt tweak
    - keep both paths open:
      - fix the current LLM route-hint contract
      - replace the route-hint call with a simpler deterministic classifier if the LLM contract remains unreliable
    - treat that replace option as donor-first-consistent, not donor drift

Recommended next step:
- plan `20.8`

Recommended agent effort:
- xhigh

### Phase 20.8. Route-Hint Reliability Fix-Vs-Replace Decision
Wave:
- Routing Reliability
- Restoration

Depends on:
- Phase 20.7

Purpose:
- isolate route-hint reliability as its own bounded live blocker
- begin with raw route-hint output audit rather than blind prompt tweaking
- decide explicitly whether to:
  - fix the current LLM route-hint contract
  - or replace the LLM route-hint call with a simpler deterministic classifier
- restore safe structural route activation without reopening broad fact-path or profile retrieval work

Hard rules:
- this phase must start with raw route-hint output audit
- this phase must keep both paths open until the audit is complete:
  - fix the current LLM route-hint contract
  - replace the route-hint call with a simpler deterministic classifier
- this phase must not assume prompt tightening is the only valid answer
- this phase must not silently coerce explanatory prose into a route
- this phase must not grow a multilingual keyword / alias routing table
- this phase must not reopen fact-path parity or profile / identity retrieval as its main scope
- this phase must distinguish route activation from temporal / aggregate channel candidate yield
- this phase must end with isolated route-hint validation plus comparable live reruns
- benchmark evidence remains diagnostic, not the product goal; the target is a better everyday kernel

Current recorded rationale:
- `20.8` resolved its narrow decision in favor of `replace`, not `fix`
- the old LLM route-hint path remained unreliable for two independent reasons:
  - historical raw outputs were explanatory prose, not machine-usable route tokens
  - the auxiliary-client LLM route-hint path still hit `401` in the target runtime
- the bounded deterministic route-hint path is now the chosen default route-hint path
- comparable live reruns after replacement showed:
  - answer-only: `2 / 15`
  - split raw answer: `5 / 15`
  - split `retrieval_correct`: `3 / 15`
  - split `both_correct`: `3 / 15`
- route activation is now restored instead of collapsing to fallback:
  - `deterministic_route_hint`: `14 / 15`
  - `default`: `1 / 15`
  - requested/applied modes:
    - `fact`: `7`
    - `temporal`: `6`
    - `aggregate`: `2`
- route activation did not solve downstream retrieval quality
- temporal / aggregate channel yield remains partial:
  - activated temporal routes with nonzero temporal-channel yield: `2 / 6`
  - activated temporal routes with zero temporal-channel yield: `4 / 6`
  - activated aggregate routes with nonzero graph yield: `1 / 2`
  - activated aggregate routes with zero graph yield: `1 / 2`
- therefore `20.8` is treated as a routing-success / retrieval-quality-failure phase
- this explicitly carries forward fact-path parity, profile retrieval, temporal-channel yield, and candidate-quality / packing recovery into `20.9`
- `20.9` must also explicitly re-audit deterministic classifier misroutes before reading temporal yield as route-quality truth
  - false-positive temporal routing and false-negative temporal routing both matter
- if the deterministic gate hurts more cases than it helps, bounded multi-channel fusion / soft routing remains the explicit fallback policy alternative
- aggregate counting remains an opportunity-cost warning under the current architecture
  - not a hard numerical ceiling
  - not the dominant target function for the next phase

Recommended next step if gate passes:
- plan `20.9`

Recommended agent effort:
- xhigh

### Phase 20.9. Fact-Path Parity, Profile Retrieval, And Structural Route Quality Recovery
Wave:
- Restoration
- Retrieval Recovery

Depends on:
- Phase 20.8

Purpose:
- restore live fact-path parity against the older stronger decomp-off path once route-hint reliability is no longer the main gate
- recover the named profile / identity retrieval miss class as a first-class retrieval problem
- recover route-policy correctness, temporal-channel candidate yield, and downstream candidate quality on newly activated structural routes without reopening route-hint contract work

Hard rules:
- this phase must not be used to retry route-hint reliability from scratch
- fact-path parity must remain the first explicit workstream
- profile / identity retrieval misses must stay named explicitly
- deterministic classifier misroutes must be audited explicitly before temporal yield is read as route-quality truth
- if the deterministic gate hurts more cases than it helps, bounded multi-channel fusion / soft routing must remain an explicit fallback policy alternative
- temporal / aggregate candidate quality and packing must be named explicitly rather than hidden under generic retrieval language
- aggregate counting remains an opportunity-cost warning, not a hard numerical ceiling and not the dominant target function
- this phase must not reopen `20.2` overlay tuning or decomposition revival
- benchmark evidence remains diagnostic, not the product goal; the target is a better everyday kernel

Current recorded rationale:
- `20.9` source-side fixes were real and locally validated:
  - `44 passed`
- the first live `20.9` readings were partially invalid because they ran against a stale Bestie runtime instead of the patched source parity
- after explicitly restoring source-vs-Bestie runtime parity, the valid comparable answer-only rerun landed at:
  - `5 / 15`
- valid answer-only route/mode distribution on the patched runtime:
  - `deterministic_route_hint`: `14 / 15`
  - `default`: `1 / 15`
  - applied `fact`: `8`
  - applied `temporal`: `5`
  - applied `aggregate`: `2`
- valid answer-only activated-route yield:
  - temporal nonzero: `3 / 5`
  - temporal zero: `2 / 5`
  - aggregate nonzero graph yield: `1 / 2`
  - aggregate zero graph yield: `1 / 2`
- targeted live improvements are now visible on the patched runtime:
  - `c8c3f81d` passes on correct `fact` routing
  - `6c49646a` passes on correct `aggregate` routing
- targeted live failures also remain real:
  - `5d3d2817` remains the named profile / identity retrieval miss class
  - `0db4c65d` can activate `temporal` while still getting zero temporal candidates
  - `gpt4_7f6b06db` can activate `temporal` with nonzero candidates but still poor candidate quality
  - `f523d9fe` remains consistent with false-positive temporal routing
- this means the deterministic classifier's documented live misroute set is now larger than the original `20.8` audit set
- the comparable full split rerun did not finish cleanly enough to be treated as final `20.9` truth
- therefore the dominant carry-forward lesson from `20.9` is no longer only retrieval quality:
  - runtime-sync verification must become a hard precondition for every benchmark/harness run
  - the current full `15`-question split loop is too slow and too operationally fragile to remain the default inner-loop diagnostic tool
  - the fixed `5`-question canary can stay stable, but `f523d9fe` must be named as an explicit route-harness audit case in `20.10` even outside that canary

Recommended next step if gate passes:
- plan `20.10`

Recommended agent effort:
- xhigh

### Phase 20.10. Benchmark Validation, Runtime Sync, And Fast-Feedback Harnesses
Wave:
- Validation
- Harness Hardening

Depends on:
- Phase 20.9

Purpose:
- harden the Brainstack benchmark workflow so future retrieval-recovery phases can iterate with fast, trustworthy evidence
- add runtime-sync verification before any harness or benchmark run
- build retrieval-quality harnesses that do not require full answer/judge loops
- define a fixed canary subset and demote full `15`-question live runs to phase-gate proof only

Hard rules:
- runtime-sync verification must be step `0` for benchmark/harness execution
- this phase must not become a generic retrieval-fix phase
- the retrieval-quality harness must expose route, candidates, and packed memory context without answer/judge loops
- the fixed `5`-question canary must remain stable once named
- `f523d9fe` must be included explicitly in route-harness audits even though it is outside the fixed canary
- full `15`-question live answer-only / split reruns must move out of the default inner loop
- benchmark evidence remains diagnostic, not the product goal; the target is a faster and more trustworthy iteration loop

Current recorded rationale:
- `20.9` established a more honest live truth only after explicit runtime-parity repair:
  - valid patched-runtime answer-only: `5 / 15`
- `20.9` also showed that the current benchmark loop is too fragile and too slow for routine diagnosis:
  - stale Bestie runtime distorted earlier live readings again
  - full split reruns remained partial / unstable and too expensive to keep as the default inner loop
- the next highest-leverage move is therefore validation/harness hardening, not another immediate full retrieval-fix phase
- required carry-forward components are now explicit:
  - runtime-sync verification as step `0`
  - retrieval-quality harness as the first new deliverable
  - fixed `5`-question canary:
    - `c8c3f81d`
    - `5d3d2817`
    - `e9327a54`
    - `gpt4_7f6b06db`
    - `6c49646a`
  - route-harness cleanup with explicit `f523d9fe` audit coverage outside the fixed canary
  - full `15`-question live runs used as phase-gate proof only
- `20.10` execution has now delivered those harness goals:
  - runtime-sync verification is implemented as a hard step `0`
  - the actual check against the current Bestie root compared `28` files and found `0` mismatches
  - retrieval-quality harness exists via runner `--retrieval-only`
  - fixed canary execution exists via runner `--canary`
  - route-harness cleanup is complete and deterministic canary + extra-case sanity ran successfully
  - targeted local validation passed:
    - `22 passed`
    - `py_compile` clean on `4` modified files
- `20.10` should therefore be read as a workflow/harness phase, not a retrieval-quality success claim
- the next retrieval phase should consume the new fast-feedback ladder instead of defaulting back to full `15`-question inner-loop reruns
- `20.11` should start with a runtime-sync-passing, patched-runtime retrieval-harness baseline on the fixed canary before any new retrieval code is changed
- a local checkpoint commit of the completed `20.10` harness state is recommended before `20.11`, to reduce source/runtime/history drift during later retrieval phases

Recommended next step if gate passes:
- execute `20.11`

Recommended agent effort:
- xhigh

### Phase 20.11. Canary-First Retrieval Recovery For Fact Parity And Structural Quality
Wave:
- Restoration
- Retrieval Recovery

Depends on:
- Phase 20.10

Purpose:
- use the `20.10` harness ladder to recover real retrieval quality on the fixed canary before spending more full-benchmark time
- restore live fact-path parity on the canary fact/profile cases
- recover structural route quality on the canary temporal/aggregate cases

Hard rules:
- the first `20.11` action must be a runtime-sync-passing patched-runtime `--retrieval-only --canary` baseline reading
- no retrieval code change should precede that baseline artifact
- the fixed `5`-question canary must remain stable
- `5d3d2817` must remain a named profile / identity retrieval class
- `f523d9fe` must remain an explicit route-audit case outside the canary
- structural route analysis must separate:
  - route selection
  - candidate quality / channel yield
  - evidence packing
- full `15`-question live runs must remain outside the inner loop unless canary evidence justifies them
- aggregate counting remains an opportunity-cost warning, not the dominant target function

Current recorded rationale:
- LongMemEval remains a calibration probe, not the product objective
  - the real target is a SOTA Hermes memory kernel with coherent continuity, proactive state tracking, long-range usable recall, and meaningful token savings
  - benchmark-specific benchmaxing drift is explicitly disallowed
- `20.10` delivered the tools needed for fast, trustworthy retrieval iteration:
  - runtime-sync verification
  - retrieval-only harness
  - fixed canary execution
  - route-harness cleanup
- therefore `20.11` should begin with instrument reading, not with code
- the next retrieval phase should answer these concrete questions first:
  - why is fact-path parity still weak on patched runtime?
  - why does `5d3d2817` still miss profile / identity retrieval?
  - on structural routes, is the dominant problem route selection, candidate quality, or packing?
- only after that baseline exists should retrieval code be touched
- the required patched-runtime `--retrieval-only --canary` baseline has now completed:
  - runtime sync:
    - `ok: true`
    - `compared_files: 28`
    - `mismatch_count: 0`
  - canary completed:
    - `5 / 5`
    - elapsed: `344.904s`
    - `memory_context_present: 5 / 5`
    - non-fact routes: `2 / 5`
- the baseline already narrows the dominant blockers:
  - `5d3d2817` remains a profile / identity miss even though relevant transcript rows were previously proven to exist in storage
  - `e9327a54` is now a confirmed fact-path packing win in the patched canary
  - `gpt4_7f6b06db` now activates `temporal` cleanly in the live canary, so the old blocker is no longer route-policy contamination
  - `6c49646a` shows the aggregate route is not blank because graph yield is nonzero (`6`)
- later `20.11` follow-up tightened the diagnosis further:
  - a real half-wired live-path bug existed in `db.py` (`profile_priority_adjustment` referenced without import) and is now fixed
  - a source/runtime route-policy drift was found and corrected:
    - the source had drifted back to the LLM route-hint path instead of the recorded bounded deterministic default
    - the deterministic default resolver is now restored in source and resynced to Bestie
  - a generic transcript-row prioritization patch produced one real live win:
    - `e9327a54` now surfaces `turn 50` / Sugar Factory first in the patched canary transcript block
  - a later bounded carry-through / budget rebalance pass improved `5d3d2817`
    - a structural continuity-to-transcript carry-through join bug was identified and fixed
      - continuity and transcript rows for the same turn did not share raw `id`, so the carry-through now joins on `session_id + turn_number`
    - the final live packed memory block now includes the answer-bearing marketing-specialist transcript row (`turn 126`) alongside the later senior-marketing-analyst row (`turn 128`)
    - the targeted patched-runtime retrieval harness now answers this case correctly
    - so this is no longer a pure carry-through miss; the remaining blocker is residual junk suppression / packing around an already-present answer-bearing row
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
    - therefore the remaining blocker is temporal candidate generation / extraction first, then downstream packing
  - the latest completed retrieval-only canary now also confirms the faster loop shape:
    - `5 / 5` completed in `303.93s`
    - `memory_context_present: 5 / 5`
    - non-fact routes: `2 / 5`
  - a later post-join-fix canary retrieval-only rerun sharpened the current target again:
    - runtime sync still held (`28` compared files, `0` mismatch)
    - `5 / 5` completed in `318.259s`
    - `5d3d2817` now answers correctly in retrieval-only mode with the answer-bearing `turn 126` marketing-specialist transcript row present in the final live memory block
    - `gpt4_7f6b06db` still runs as `temporal` with nonzero structural counts (`temporal: 14`, `graph: 8`), but the final live memory block still misses the actual trip set
    - targeted current-debug further shows the real trip rows are largely absent from the fused pool, not merely dropped at the last packing step
    - so the current leading unresolved blocker is activated non-fact route candidate generation / extraction, with packing still secondary, and no longer the old pure carry-through miss on `5d3d2817`
  - a bounded temporal shortlist variant was also tested and rejected:
    - a strict relevance-shortlist-then-chronology strategy made `gpt4_7f6b06db` worse by surfacing generic “past three months” fitness/stamps rows
    - the patch was reverted immediately
    - therefore the next temporal fix should not be another naive lexical/semantic shortlist tweak over the current signals
  - a second bounded temporal query-form variant was also tested and rejected:
    - a route-aware focused-search-query variant made `gpt4_7f6b06db` worse by shifting transcript evidence toward Kyoto / attachment junk instead of the real trip set
    - the patch was reverted immediately
    - therefore the next temporal fix should not be naive temporal query shaping or frame-token stripping over the current signals
  - a third bounded temporal search-limit variant was also tested and rejected:
    - a temporal-route widening of continuity / transcript / semantic candidate-pool limits increased raw channel counts but still selected the same off-target turns (`matched: 25, 37, 35`; `transcript: 37, 38, 35`)
    - the real Muir Woods / Big Sur / Yosemite trip set still did not surface
    - the patch was reverted immediately
    - therefore the next temporal fix should not be bounded search-pool widening over the current retrieval signals
  - a donor-first structured temporal-event path is now also implemented and locally validated:
    - Tier-2 can emit bounded `temporal_events` tied to real transcript `turn_number`s
    - reconciliation persists them as `temporal_event` continuity rows with temporal metadata
    - bounded validation stayed green (`48` source-targeted tests, `25` plugin-namespace real-world flow tests)
  - the first targeted patched-runtime reruns after that temporal-event path still do **not** prove live retrieval recovery on `gpt4_7f6b06db`:
    - the answer string may come back correct
    - but the captured memory context still omits `Muir Woods`, `Big Sur`, and `Monterey`
    - so this remains unsupported answer recovery, not retrieval success
  - parser-context instrumentation now also shows:
    - live non-JSON Tier-2 failures happen on unrelated batch windows such as `turns=[89..96]`, `turns=[185..192]`, and `turns=[270..277]`
    - therefore Tier-2 JSON truncation is real but not yet proven as the direct cause of the trip-order miss
- a later benchmark-path Tier-2 telemetry pass tightened that reading further:
  - the benchmark runner was confirmed to use unusually fat seed settings by default:
    - `flush interval = 96`
    - `transcript limit = 192`
  - under that default `96/192` path, the targeted `gpt4_7f6b06db` rerun still had very sparse structural population:
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
    - route channels improved to `graph: 4`, `temporal: 10`
  - but the final selected evidence still stayed off-target for the trip-order case
  - a follow-up `32/32/900` probe then ruled out the simplest truncation story:
    - `parse_status_counts` degraded from `{"non_json": 6, "json_object": 3}` to `{"non_json": 7, "json_object": 2}`
    - `total_writes` dropped from `32` to `14`
    - therefore “just raise Tier-2 max tokens” is now explicit negative evidence, not the fix
  - a richer `32/32/400` telemetry run then made the remaining seed-time failure shape concrete:
    - `parse_status_counts: {"empty_text": 1, "non_json": 5, "json_object": 3}`
    - successful write-bearing windows are now visible:
      - `97..128`
      - `193..224`
      - `230..277`
    - failing windows are also visible:
      - `1..32` as `empty_text`
      - `31..64`, `65..96`, `124..160`, `161..192`, `225..256` as `non_json`
    - several `non_json` previews begin with JSON-like objects rather than obvious prose
    - therefore the next concrete `20.11` move should be raw payload failure-mode reading first, then parser/prompt/schema choice second
  - two follow-up structural fixes then moved the bottleneck forward again:
    - compact Tier-2 output-shape rules
    - temporal-route selection wired to `temporal_graph_rows`
  - after those fixes, the targeted `gpt4_7f6b06db` rerun improved to:
    - `parse_status_counts: {"non_json": 2, "json_object": 7}`
    - `batches_with_writes: 7`
    - `total_writes: 69`
    - backend population: `entity=6`, `state=8`, `relation=1`, `inferred=3`
    - the previously failing Yosemite window `225..256` now parses as `json_object` with `temporal_events=7`
  - that means the relevant trip evidence is now being extracted, but still not surfaced into the final memory block
  - so the current live blocker has moved again:
    - no longer primarily seed-time Tier-2 reliability
    - now temporal-event surfacing / continuity selection into final memory
  - a follow-up query-aware temporal-event surfacing pass then narrowed that blocker one more step:
    - temporal mode now has an explicit cross-session `temporal_event` retrieval path with query-aware ordering
    - this produced the first live surfacing win where one relevant Yosemite temporal-event row reached the final `recent` block
    - but the full `Muir Woods -> Big Sur/Monterey -> Yosemite` chain still did not surface together
    - so the remaining blocker is now multi-event temporal continuity ranking / selection breadth rather than total absence of temporal-event surfacing
  - a later `temporal_event_samples` rerun then corrected the emphasis again:
    - the relevant trip window `225..256` regressed back to `json_parse_status = non_json`
    - it produced `writes_performed = 0`, `temporal_events = 0`, and no temporal-event samples
    - its raw payload stayed visibly JSON-like and trip-related, but truncated / unparsable
    - so the primary blocker is currently better described as trip-window Tier-2 parser / output-shape instability, not temporal ranking direction alone
  - the next control reruns then refined that again:
    - Tier-2 reasoning-field fallback materially improved admission reliability on the targeted trip-order case
    - the no-direct control run removed the `empty_text` class and wrote the relevant trip batch successfully with temporal events
    - this means the trip-window is no longer best described as “failing to admit” on the current patched path
    - but the final temporal selected block still does not surface the full ordered trip chain
  - two more bounded fixes were then tried against that narrower blocker:
    - temporal continuity prioritized ahead of generic recent continuity
    - lexical-hygiene cleanup for obviously noisy retrieval stopwords such as `the` / `from`
  - neither was sufficient to close the live trip-order miss
  - therefore the current `20.11` temporal blocker is now best read as:
    - the right trip-window evidence can be admitted and stored
    - the route can be genuinely temporal on the no-direct control path
    - but temporal continuity relevance discrimination is still too weak when multiple temporal_event rows compete for the final selected block
- final `20.11` gate reading:
  - cheap structural donor-first fixes delivered real generic value in this phase
  - the residual `gpt4_7f6b06db` miss is no longer best read as route activation, basic seed admission, or another small temporal heuristic gap
  - the remaining blocker is temporal-event relevance discrimination once many structured temporal rows compete for the final selected block
  - this should now move out of `20.11` and into a dedicated capability phase rather than more `20.11` micro-tuning
- the recorded medium-term path beyond `20.11` is now explicit:
  - short-term recovery should focus on Tier-2 seed reliability / structural population, then temporal extraction / evidence yield, packing quality, and bounded grounding carry-through
  - the `5d3d2817` canary truth also sharpened the architecture reading:
    - the answer-bearing profile evidence now reaches the final live memory block after the structural join fix
    - therefore the immediate bottleneck is junk-heavy fusion / packing, not pure evidence absence
    - a later asymmetric reranker / stronger-embedder phase would be attacking the same bottleneck at a stronger implementation layer, not a different class of problem
    - the project should therefore exhaust the cheap internal fusion / packing path first, then escalate only if the canary stops improving
  - if aggregate-counting remains structurally weak after those fixes, the next donor-first architectural path is:
    1. stronger Tier-2 typed entity extraction
    2. then a bounded native Kuzu aggregate query path for count/sum-style aggregate questions
  - separately, a future profile / identity retrieval phase may evaluate:
    - stronger asymmetric reranking over top-K fused candidates
    - or a stronger semantic retrieval backbone
    - but this should be framed as a capability-phase candidate, not as an already-chosen vendor/model commitment
  - if a named candidate needs to be carried forward for that future evaluation, the current tentative brand-level front-runner is the Jina v5 text-embedding family through a TEI-style serving path
    - treat this as a soft evaluation candidate only
    - do not convert it into a hard architectural rule before a real project-local bakeoff
  - this is recorded as a forward path, not as a proven score guarantee or hard numerical ceiling
  - planning hygiene follow-up should also be carried forward:
    - once the active retrieval critical path is no longer the main blocker, create a compact current-state artifact (`STATE-COMPACT.md` or equivalent)
    - keep the full append-only `STATE.md` / `ROADMAP.md` as the historical record
    - the compact artifact is for faster orientation, not for replacing history

Recommended next step if gate passes:
- plan `20.12`

Recommended agent effort:
- xhigh

### Phase 20.12. Temporal-event semantic retrieval and reranking capability for structured continuity
Wave:
- Capability
- Retrieval Quality

Depends on:
- Phase 20.11

Purpose:
- turn the residual `gpt4_7f6b06db`-class temporal miss into a general memory-kernel capability problem rather than another `20.11` micro-tuning loop
- add a bounded semantic retrieval / reranking layer over structured `temporal_event` continuity evidence
- preserve donor-first behavior and anti-benchmaxing discipline while testing a stronger relevance layer

Hard rules:
- do not reopen route-hint work
- do not reopen failed shortlist / query-shaping / pool-widening experiments
- do not write benchmark-row-specific cues or exceptions
- keep LongMemEval as a calibration probe, not the target function
- keep Jina v5 TEI as a soft evaluation candidate only, not a hard vendor lock
- keep full `15`-question live runs outside the inner loop unless retrieval-only evidence justifies them

Current recorded rationale:
- `20.11` delivered the cheap structural donor-first wins that were still clearly justified:
  - patched-runtime canary truth
  - join-bug closure on `5d3d2817`
  - restored deterministic route truth
  - compact Tier-2 schema and JSON repair improvements
  - reasoning fallback
  - explicit `temporal_event` surfacing
- after those wins, the residual temporal gap no longer looks like another cheap internal fix:
  - route activation is no longer the blocker
  - the relevant trip window can now be admitted and written
  - structured temporal evidence can now be surfaced
  - the remaining miss is better read as temporal-event relevance discrimination once many structured rows compete for the final selected block
- therefore `20.12` should be planned as a capability phase:
  - bounded hybrid over temporal-event candidates first
  - semantic retrieval over temporal-event rows if needed
  - stronger external semantic layer only if the bounded internal route proves too weak
- this phase should stay generic and donor-first:
  - memory-kernel capability framing
  - no benchmark-maxing
  - no premature vendor lock
  - be slightly more permissive in evaluation order if needed:
    - Jina v5 TEI is the preferred external evaluation candidate
    - but still not a hard architectural mandate
    - if evaluated, prefer CPU-first TEI bring-up with cache volume, healthcheck, fixed retrieval command, and `last-token` pooling before GPU

Plans:
- [ ] `20.12-01-PLAN.md` — temporal-event semantic retrieval / reranking capability for structured continuity

Recommended next step if gate passes:
- execute `20.13`

Recommended agent effort:
- xhigh

Execution update:
- `20.12` is execution-complete at gate
- a bounded temporal semantic rerank layer now exists in code
- an env-gated stronger external scorer path also exists in code
  - Jina v5 TEI earned preferred external evaluation status through local evidence
  - but it did not solve the target live miss on its own
- the targeted `gpt4_7f6b06db` proofs showed:
  - the semantic scorer path is now real and stable
  - but the relevant trip temporal-event chain still does not reliably appear in the bounded live temporal pool
- the fixed canary retrieval-only run with the Jina-gated scorer showed no obvious fact/profile/aggregate collateral regression
- therefore the residual blocker after `20.12` is not “we still need a reranker”
- the residual blocker is upstream temporal-event candidate availability / generation reliability

### Phase 20.13. Upstream temporal-event candidate availability and generation reliability
Wave:
- Capability
- Retrieval Quality

Depends on:
- Phase 20.12

Purpose:
- follow the `20.12` gate handoff without reopening scorer-tuning as the main question
- localize where the desired temporal-event chain drops out before reranking:
  - generation
  - persistence
  - cross-session surfacing
  - bounded pool assembly
  - or pre-rerank filtering
- land one bounded generic upstream fix if the dominant dropout point is clear enough

Hard rules:
- do not reopen route-hint work
- do not reopen benchmark-specific lexical tuning
- do not re-litigate whether a semantic reranker exists
- preserve the bounded temporal semantic rerank layer and the env-gated external scorer hook
- keep LongMemEval as a calibration probe, not the target function
- keep Jina v5 TEI as a preferred external candidate only, not a hard vendor lock

Current recorded rationale:
- `20.12` proved that the scorer layer is now real:
  - bounded hybrid temporal-event reranking exists
  - stronger external scoring can be evaluated without a full backend migration
  - Jina v5 TEI earned preferred external evaluation status through local evidence
- `20.12` also proved the current limit of scorer-side work:
  - stronger scoring alone did not fix the live `gpt4_7f6b06db` miss
  - the relevant trip temporal-event chain still did not reliably appear in the bounded live temporal pool
- therefore the next follow-up should not ask “do we need a reranker?”
- the next follow-up should ask:
  - where does the desired temporal-event chain drop out before reranking?
  - what is the smallest generic upstream fix that makes the reranker see a better pool?
- this phase should stay generic and donor-first:
  - memory-kernel capability framing
  - no benchmark-maxing
  - no vendor lock
  - no reopening of already settled scorer capability questions

Plans:
- [ ] `20.13-01-PLAN.md` — upstream temporal-event candidate availability and generation reliability

Recommended next step if gate passes:
- add and plan `20.14`

Recommended agent effort:
- xhigh

Execution update:
- `20.13` is execution-complete at gate
- session-clean DB audits localized the dominant upstream blocker more sharply than the `20.12` handoff:
  - under the default benchmark-path flush, the desired `Muir Woods -> Big Sur/Monterey -> Yosemite` chain did not reliably persist as `temporal_event` continuity rows
  - `32/32` improved structural population but still left only a partial chain
  - `16/16` increased writes further but worsened parse stability
- isolated original-session extraction proved the current extractor can generate the missing trip chain when fed the original answer sessions cleanly:
  - Muir Woods events from `answer_5d8c99d3_1`
  - Big Sur / Monterey plus Yosemite events from `answer_5d8c99d3_2`
  - Yosemite / JMT events from `answer_5d8c99d3_3`
- the bounded upstream fix now in code is:
  - `--benchmark-tier2-flush-mode session_boundary`
  - with exact session-turn transcript override per flush
- a real Kuzu duplicate-primary-key republish bug was found during this proof and fixed:
  - repeated publication of the same `State` / `Conflict` ids now uses `MERGE` + `SET` instead of `CREATE`
- the strongest bounded proof is the oracle-only session-boundary rerun:
  - with `400` tokens the first session still repaired partially and dropped Muir Woods events
  - with `900` tokens all three answer-session batches returned `json_object`
  - the desired trip chain was restored across those batches
- the full haystack session-boundary proof was intentionally stopped after it remained too expensive for the inner loop once the crash was fixed
  - it is not accepted as the phase-closing proof artifact
- the post-fix retrieval-only canary rerun completed with runtime sync still clean:
  - `28` compared files
  - `0` mismatches
  - `5 / 5` canary items completed
  - no obvious fact/profile/aggregate collateral regression on manual answer inspection
- therefore the residual blocker after `20.13` is no longer pure upstream temporal-event absence
- the residual blocker is temporal chain coverage / final selection breadth over now-available session-aligned events

### Phase 20.14. Temporal chain coverage, diversity, and selection-cap rebalance
Wave:
- Capability
- Retrieval Quality

Depends on:
- Phase 20.13

Purpose:
- follow the `20.13` gate handoff without reopening scorer or generation confusion
- localize why restored temporal events still compress into an incomplete final chain:
  - cap arithmetic
  - diversity failure
  - dedupe collapse
- land one bounded generic selection-layer fix if the dominant compressor is clear enough

Hard rules:
- do not reopen route-hint work
- do not reopen scorer-vs-availability debate
- do not reopen upstream batch-composition work as the main thread
- do not write benchmark-row-specific trip rules
- keep LongMemEval as a calibration probe, not the target function
- preserve `session_boundary` only as a bounded benchmark-path proof tool, not a product-path retrieval rule

Current recorded rationale:
- `20.13` restored the desired trip chain under bounded oracle proof:
  - Muir Woods
  - Big Sur / Monterey
  - Yosemite
- the residual miss now sits at the final temporal selection layer:
  - too-small temporal caps can over-compress the chain
  - one trip can consume multiple slots while another gets none
  - row-level dedupe may still interact with that compression and must be checked explicitly
- therefore the next follow-up should not ask “can the events be generated?”
- the next follow-up should ask:
  - how do we preserve enough distinct trip coverage once those events exist?
  - what is the smallest generic fix that restores that coverage?
- this phase should stay generic and donor-first:
  - memory-kernel capability framing
  - no benchmark-maxing
  - no reopening of settled scorer or generation questions

Plans:
- [ ] `20.14-01-PLAN.md` — temporal chain coverage, diversity, and selection-cap rebalance

Recommended next step if gate passes:
- execute `20.15`

Recommended agent effort:
- xhigh

Execution update:
- `20.14` is execution-complete at gate
- the dominant residual blocker after `20.13` was not renewed generation failure and not scorer drift
- the dominant blocker was bounded temporal selection over-compression:
  - one temporal bucket could consume multiple limited slots
  - `recent` and `matched` could also reuse the same rows, wasting coverage
- the winning fix was a bounded combination:
  - temporal bucket diversity inside temporal selection
  - explicit non-reuse of already selected temporal rows across `recent` / `matched`
- no cap increase was required to prove the named chain
- the strongest bounded proof now passes on the handoff case:
  - retrieval-only
  - oracle-only
  - `session_boundary`
  - `--benchmark-tier2-max-tokens 900`
  - correct Muir Woods -> Big Sur/Monterey -> Yosemite answer text
- the post-fix retrieval-only canary also stayed clean:
  - runtime sync `28 / 28` with `0` mismatches
  - `5 / 5` canary items completed
  - no obvious fact/profile/aggregate collateral regression on manual answer inspection
- therefore the main open capability path after `20.14` is no longer temporal trip-chain selection
- the cleaner forward path is:
  1. stronger Tier-2 typed entity extraction
  2. then a bounded native Kuzu aggregate query path for count/sum-style aggregate questions

### Phase 20.15. Tier-2 typed entity extraction and bounded Kuzu aggregate query capability
Wave:
- Capability
- Retrieval Quality

Depends on:
- Phase 20.14

Purpose:
- follow the `20.14` closeout without reopening temporal micro-tuning
- turn the recorded medium-term aggregate forward path into a bounded capability step
- improve Tier-2 typed entity extraction enough to support one bounded native Kuzu aggregate query class

Hard rules:
- do not reopen temporal-chain rescue as the main thread
- do not reopen scorer / reranker debate
- do not solve aggregate questions by lexical counting hacks
- do not write benchmark-specific entity or event rules
- keep LongMemEval as a calibration probe, not the target function
- preserve `session_boundary` only as a bounded benchmark-path proof tool

Current recorded rationale:
- `20.14` closed the temporal selection handoff at gate with a bounded diversity + non-reuse fix
- the cleaner next capability seam is the one already carried forward in project notes:
  1. stronger Tier-2 typed entity extraction
  2. then a bounded native Kuzu aggregate query path for count/sum-style aggregate questions
- aggregate recovery should now be approached structurally:
  - better typed graph structure
  - bounded native graph queries
  - not prompt-side counting over packed rows
- execution guard additions for this phase:
  - classify the named aggregate proof case before query work (`count`, `sum`, grouped comparison, or another explicit class)
  - keep Tier-2 prompt changes additive to the current temporal-event extraction rules
  - preserve the current temporal-event hard caps, concrete-event preference, and prior-event capture rules unless explicit regression evidence shows one is itself the blocker
  - keep the fixed temporal canary case `gpt4_7f6b06db` green after any Tier-2 prompt change
  - if typed extraction grows larger than the bounded phase shape, allow an honest `20.16` deferral for the native Kuzu aggregate query path instead of forcing both capabilities into one phase
- this phase should stay generic and donor-first:
  - memory-kernel capability framing
  - no benchmark-maxing
  - no reopening of already-closed temporal questions unless a fresh generic regression appears
- execution closeout:
  - initial live proof stayed correct on the named aggregate case but still surfaced transcript evidence rather than a native graph row
  - the decisive localization truth came from the real `session_boundary` benchmark-derived graph state:
    - aggregate-capable typed structure did exist
    - the final blocker was planner/query shape mismatch against live typed entity forms such as `mileage_history` and `family_road_trip`
  - the bounded closeout therefore landed two real wins together:
    - typed aggregate-capable graph structure is now written
    - one bounded native Kuzu sum path now surfaces a real `native_aggregate` row over that graph state
  - this phase does **not** claim that every mixed benchmark-path aggregate case now automatically prefers the native row by default

Plans:
- [x] `20.15-01-PLAN.md` — Tier-2 typed entity extraction and bounded Kuzu aggregate query capability

Recommended next step if gate passes:
- add and plan `20.16`
- treat the next aggregate seam as broader typed aggregate coverage and broader native aggregate query coverage, not re-proving the bounded `20.15` class
- carry forward two explicit `20.15` constraints into `20.16` planning:
  - the current native aggregate planner is still intentionally narrow around the proven total-distance road-trip sum class and should be broadened honestly rather than overclaimed
  - the current Kuzu aggregate path still relies on bounded Python-side post-filtering over an over-fetched candidate slice, which is acceptable for the bounded proof but should be revisited if broader aggregate coverage increases graph fan-out

Recommended agent effort:
- xhigh

Execution update:
- `20.15` is execution-complete at gate
- the initial live named-case proof stayed correct but still surfaced transcript evidence rather than a native graph row
- the decisive localization truth came from the real `session_boundary` benchmark-derived graph state:
  - aggregate-capable typed graph structure did exist
  - the dominant blocker was planner/query shape mismatch against real typed forms such as `mileage_history` and `family_road_trip`
- the bounded closeout landed two real wins together:
  - stronger Tier-2 typed extraction now writes aggregate-capable graph structure
  - one bounded native Kuzu sum path now surfaces a real `native_aggregate` row over that graph state
- the post-change retrieval-only canary stayed structurally stable:
  - runtime sync `28 / 28` with `0` mismatches
  - `5 / 5` canary items completed with memory context present
  - no obvious fact/profile route-collapse regression
- this phase does **not** claim that the default mixed benchmark path now automatically prefers the native aggregate row in every aggregate case
- completed broader spillover note before `20.16`:
  - the non-gate `70`-item oracle retrieval-only spillover confirmed meaningful structural spillover beyond the fixed canary:
    - `fact/fact`: `31`
    - `aggregate/aggregate`: `21`
    - `temporal/temporal`: `17`
    - `temporal/fact`: `1`
    - `memory_context_present`: `70 / 70`
  - but it also surfaced a broad oracle-visible Tier-2 residual class:
    - `backend_population_nonzero`: `48 / 70`
    - `zero_backend_cases`: `22 / 70`
    - `empty_text_batches`: `19`
    - `19` of the `22` zero-backend cases overlapped `empty_text`
  - the stronger current reading is that this oracle residual is primarily a runner-configuration artifact:
    - `--oracle-seed` restricts the seed to answer-session IDs
    - the wider oracle run used the default benchmark flush shape rather than the stronger bounded proof configuration
  - the smaller `12`-item live retrieval-only spillover was materially healthier:
    - `fact/fact`: `5`
    - `aggregate/aggregate`: `4`
    - `temporal/temporal`: `3`
    - `memory_context_present`: `12 / 12`
    - `backend_population_nonzero`: `12 / 12`
    - `zero_backend_cases`: `0`
    - `empty_text_batches`: `0`
  - the next phase therefore should not assume either:
    - that aggregate broadening can ignore the oracle residual entirely
    - or that the oracle residual automatically dominates the live path
  - instead `20.16` should keep the broader aggregate capability thread as the main line, while carrying forward the short-session oracle admission behavior as a bounded edge-case note

### Phase 20.16. Live residual bridge triage before broader aggregate expansion
Wave:
- Capability
- Retrieval Quality

Depends on:
- Phase 20.15

Purpose:
- use the post-deploy live `12` answer-only evidence to identify the dominant remaining live blocker after `20.15`
- separate live bridge misses from live admission / `empty_text` residual
- decide whether broader aggregate expansion is truly next or should wait behind bridge/admission work

Hard rules:
- do not relabel the oracle short-session residual as a proven live-path blocker
- do not reopen temporal micro-tuning as the main thread
- do not solve aggregate questions with lexical counting or prompt-side arithmetic
- do not replace existing temporal-event prompt rules while broadening typed extraction
- keep LongMemEval as a calibration probe, not the target function
- keep `session_boundary` as a bounded benchmark-path proof tool only

Current recorded rationale:
- `20.15` closed at gate with a real bounded aggregate capability win:
  - stronger typed extraction now writes aggregate-capable graph state
  - one bounded native Kuzu sum path now surfaces `native_aggregate` rows on real typed graph state
- the post-`20.15` spillover read clarified the next priority:
  - the `70`-item oracle retrieval-only spillover showed broader structural generalization beyond the fixed canary
  - the `12`-item live retrieval-only spillover stayed healthy (`12 / 12` backend nonzero, `0` `empty_text`)
  - the oracle `22 / 70` zero-backend pattern is better read as an oracle-runner / short-session configuration artifact than as a proven product blocker
- the later post-deploy fixed `12`-item live answer-only slice changed that reading materially:
  - final answer accuracy landed at `6 / 12`
  - runtime sync stayed clean (`28 / 28`, `0` mismatch)
  - the live residual split was not uniform:
    - `6 / 12` cases had nonzero backend population
    - `6 / 12` cases stayed zero-backend
    - `8 / 12` cases showed at least one `empty_text` Tier-2 batch
  - `6c49646a` still passed live with the correct `3,000 miles`, but with `0` backend writes and without a surfaced `native_aggregate` row
  - `gpt4_7f6b06db` seeded nonzero backend state and `temporal_events`, but still failed answer-only live
- a stricter deployed Bestie live reset-eval then raised the bar again, but the result was confounded:
  - report: `reports/phase20/brainstack-bestie-live-reset-eval.json`
  - same synthetic user, explicit `/reset` between seed and recall across `5` short realistic conversations
  - result: `0 / 5`
  - this was not a provider/bootstrap fake failure:
    - it ran on the deployed Bestie checkout
    - it used the real deployed provider/model route (`custom` + `minimax-m2.7`)
  - the run surfaced real live concerns:
    - some seed or recall turns returned empty
    - earlier aggregate content resurfaced in the wrong later scenario
    - later recall preferred the immediately previous cafe-order memory over the intended gift-context memory
  - but the harness itself also introduced two important confounds:
    - inter-scenario bleed existed because each new scenario seed entered the prior scenario recall session before the next reset boundary
    - the eval ran on `Platform.LOCAL`, and traces showed local-tool behavior that is not faithful to deployed Discord/Bestie usage
  - review of the deployed reset path also showed that this should not be lazily explained away as `flush_min_turns`:
    - the reset path finalizes through gateway shutdown -> Brainstack `on_session_end()`
    - so `flush_min_turns` is not the main blocker supported by current evidence
- so the strongest honest post-deploy statement is now:
  - the oracle native-aggregate win is real but not yet bridged to the default live mixed path
  - admission / `empty_text` residual is still live-relevant
  - but the reset-boundary `0 / 5` result is not yet clean enough to be treated as final product truth
- the next honest seam is therefore:
  1. correct the live reset-eval harness and establish a faithful isolated baseline
  2. then re-triage the live residual split before blind aggregate expansion
  3. then decide whether the right next phase is broader aggregate coverage, live bridge work, or admission-residual work
- carry-forward note:
  - short-session oracle admission behavior should remain visible
  - but it is not the main `20.16` thread
- broader coverage should stay honest about current technical limits:
  - the current native planner is still intentionally narrow
  - the current Kuzu aggregate path still relies on bounded Python-side post-filtering over an over-fetched slice
  - if broader coverage materially increases graph fan-out, more filtering should move back into the native query path

Plans:
- [ ] `20.16-01-PLAN.md` — Live residual bridge triage before broader aggregate expansion

Recommended next step if planned:
- do **not** execute `/gsd-execute-phase 20.16` unchanged before reprioritizing against the post-deploy live answer-only evidence
- first use the revised `20.16` plan as a live bridge / admission-residual triage phase
- only then decide whether honest broader aggregate coverage is still the immediate next execute thread
- preserve additive Tier-2 temporal rules and the fixed temporal canary
- treat short-session oracle admission only as a bounded edge-case note
- strategic note after planning:
  - do not assume `20.16` execute must happen immediately
  - the accepted priority pivot is to checkpoint and deploy the accumulated `20.11`-`20.15` package into Bestie first
  - then use deployment feedback to confirm whether `20.16` remains the next highest-value phase
- checkpoint/deploy note:
  - Brainstack source checkpoint commit landed as `0b273bc`
  - Bestie integration checkpoint commit landed as `136d8bbb`
  - Bestie targeted integration validation passed (`20 passed`)
  - Bestie gateway healthcheck passed after rebuild
  - `20.16` remains planned, but execution should now be chosen against live deployment evidence rather than against planning momentum alone

Recommended agent effort:
- xhigh

Exit gate:
- the phase names the dominant live blocker honestly rather than defaulting to broader aggregate expansion
- the confounded deployed `0 / 5` reset eval is replaced by a faithful isolated live baseline
- at least one localized packet audit exists for the strongest remaining live failures
- the phase ends with an explicit next-thread decision instead of implicit planning drift

Current recorded closeout:
- `20.16` completed at gate as a live triage phase, not an aggregate-expansion phase
- corrected isolated reset eval:
  - report: `reports/phase20/brainstack-bestie-live-reset-eval-isolated.json`
  - result: `3 / 5`
  - passes:
    - `temporal_order`
    - `aggregate_total`
    - `gift_context`
  - failures:
    - `dietary_constraint`
    - `coffee_order`
- localized packet audit:
  - report: `reports/phase20/brainstack-20.16-isolated-live-packet-localization.json`
- the closeout changed the blocker reading materially:
  - the remaining failures are not simple no-write admission misses; the failing facts are persisted in transcript/continuity shelves
  - the live recall path can still surface transcript rows from unrelated isolated users/sessions
  - noun-`order` queries can still misroute into temporal mode
  - the reset/live path still ended with `profile_items = 0`, leaving preference/routine-style recall too dependent on continuity/transcript competition
- the honest next thread is therefore not broader aggregate expansion:
  - primary:
    - principal-scoped live recall isolation
    - generic `order` route disambiguation
  - secondary:
    - bounded reset-boundary bridge hardening after the isolation/routing fixes land

Recommended next step if gate passes:
- add and plan `20.17`

Recommended agent effort:
- `xhigh`

### Phase 20.17. Principal-scoped live recall isolation and route disambiguation
Wave:
- Live Recall Integrity
- Route Correctness

Depends on:
- Phase 20.16

Purpose:
- stop live recall from surfacing memories that belong to other users or unrelated sessions
- fix generic noun-`order` misrouting so requests like cafe orders do not fall into the temporal path
- harden reset-boundary recall on deployed Bestie only after principal isolation and route correctness are in place
- close out honestly whether deployed Bestie is still running with `semantic` / `graph` channels degraded, so graph/corpus-backed live enablement remains an explicit later roadmap step

Exit gate:
- the isolated live packet no longer surfaces unrelated other-session or other-user memories
- noun-`order` queries that are not temporal sequencing requests stay out of the temporal route
- if the live answer-only score stays unstable, record that honestly instead of claiming a clean gate pass

Plans:
- [x] `20.17-01-PLAN.md` — Principal-scoped live recall isolation and route disambiguation
- [x] `20.17-01-SUMMARY.md` — Principal-scoped live recall isolation and route disambiguation

Execution closeout:
- principal-scoped recall isolation was restored on the active live stack
- bare noun `order` no longer deterministically routes the `coffee_order` style case into temporal mode
- reset-boundary `session_summary` rows now preserve principal scope through the gateway finalize path
- deployed Bestie still runs with `semantic` / `graph` degraded, so `20.17` live gains are on the active `keyword + temporal` stack
- the latest repeated isolated live reset eval stayed at `2 / 5`, so `20.17` does **not** claim a clean live gate pass
- the strongest remaining structural residual is now:
  - same-principal low-overlap temporal ordering recall under the degraded live stack
- the remaining `coffee_order` / `gift_context` misses now look more like packet-use / synthesis weakness than principal leakage

Recommended next step:
- add and plan `20.18` around:
  - same-principal temporal/session-summary surfacing for low-overlap ordering recall
  - explicit packet-sufficiency vs answer-synthesis split for the remaining live fact-style failures

Recommended agent effort:
- `xhigh`

### Phase 20.19. Live graph/corpus backend enablement and post-enablement isolated re-baseline
Wave:
- Runtime Enablement
- Product Truth

Depends on:
- Phase 20.18

Purpose:
- turn the already-built `20.11–20.15` graph/corpus capability into truthful deployed Bestie runtime behavior
- stop reasoning from the degraded `keyword + temporal` stack when deciding the next live product thread
- re-baseline isolated live truth after runtime enablement instead of continuing degraded-stack micro-tuning

Exit gate:
- deployed Bestie runtime graph/corpus truth is explicit rather than ambiguous
- one post-enablement isolated live baseline exists
- the next-thread recommendation comes from enabled-stack product truth

Plans:
- [x] `20.19-01-PLAN.md` — Live graph/corpus backend enablement and post-enablement isolated re-baseline

Recommended next step:
- Add + plan Phase 20.21

Recommended agent effort:
- `xhigh`

Closeout notes:
- `20.20` is execution-complete, but not gate-complete.
- Summary:
  - `.planning/phases/20.20-enabled-stack-packet-bridge-native-aggregate-surfacing-and-live-stability/20.20-01-SUMMARY.md`
- Real bounded win:
  - aggregate route no longer hard-drops corpus rows
  - aggregate route support no longer ignores `graph_rows` / `corpus_rows`
  - source proofs cover corpus-preserving aggregate routing and corpus-only aggregate support
- Live truth after the patch:
  - post-patch isolated live baseline is `4 / 5`
    - `reports/phase20/brainstack-bestie-live-reset-eval-isolated.json`
  - focused live aggregate debug still does not show selected `native_aggregate`
    - `reports/phase20/brainstack-20.20-live-debug.json`
  - `aggregate_total` passes, but still without direct evidence of graph/corpus/native rows in the final selected packet
  - the stronger `native_total_distance` proof still fails live (`510 miles` vs expected `605`)
- Honest handoff:
  - the main residual is upstream live typed graph-state / native aggregate availability and candidate carry-through on deployed Bestie
  - the next honest step is `20.21`, not more small aggregate packet-weight tuning

Closeout notes:
- `20.19` is execution-complete at gate with a real bounded runtime enablement win.
- Bestie checkout `.venv` now imports `kuzu` and `chromadb`.
- Activation proof:
  - `reports/phase20/brainstack-20.19-activation-proof.json`
- Doctor truth:
  - `reports/phase20/brainstack-20.19-doctor.txt`
  - runtime dependency checks now pass
  - checkout-level config truth is still not fully green (`memory.provider`, builtin memory flags, absent `plugins.brainstack` section)
- Post-enablement isolated live baseline:
  - `reports/phase20/brainstack-bestie-live-reset-eval-isolated.json`
  - result: `3 / 5`
  - `aggregate_total` now passes
- Harness-faithful live debug:
  - `reports/phase20/brainstack-20.19-live-debug.json`
  - `semantic` and `graph` are both active
  - but `graph_rows` / `corpus_rows` still do not consistently win the final selected packet
- Honest handoff:
  - the main residual is now enabled-stack bridge + stability, not “backend degraded”

### Phase 20.20. Enabled-stack packet bridge, native aggregate surfacing, and live stability
Wave:
- Live Recall Quality
- Product Truth

Depends on:
- Phase 20.19

Purpose:
- turn enabled graph/corpus runtime into real final-packet influence on deployed Bestie
- prove that native aggregate evidence can actually surface on the live path
- re-baseline enabled-stack live stability before opening any broader capability thread
- start from the existing aggregate-mode native prepend path; prove or tighten its live effect rather than adding a duplicate bypass by default

Exit gate:
- there is direct evidence that enabled graph/corpus/native rows can materially surface into the final live packet
- `aggregate_total` is no longer only a transcript-arithmetic success
- one enabled-stack isolated live re-baseline exists after the bridge work
- the next-thread recommendation comes from enabled-stack truth, not fallback ambiguity

Plans:
- [x] `20.20-01-PLAN.md` — Enabled-stack packet bridge, native aggregate surfacing, and live stability

Recommended next step:
- Add + plan Phase 20.21

Recommended agent effort:
- `xhigh`

Closeout notes:
- `20.20` is execution-complete, but not gate-complete.
- Summary:
  - `.planning/phases/20.20-enabled-stack-packet-bridge-native-aggregate-surfacing-and-live-stability/20.20-01-SUMMARY.md`
- Real bounded win:
  - aggregate route no longer hard-drops corpus rows
  - aggregate route support no longer ignores `graph_rows` / `corpus_rows`
  - source proofs cover corpus-preserving aggregate routing and corpus-only aggregate support
- Live truth after the patch:
  - post-patch isolated live baseline is `4 / 5`
    - `reports/phase20/brainstack-bestie-live-reset-eval-isolated.json`
  - focused live aggregate debug still does not show selected `native_aggregate`
    - `reports/phase20/brainstack-20.20-live-debug.json`
  - `aggregate_total` passes, but still without direct evidence of graph/corpus/native rows in the final selected packet
  - the stronger `native_total_distance` proof still fails live (`510 miles` vs expected `605`)
- Honest handoff:
  - the main residual is upstream live typed graph-state / native aggregate availability and candidate carry-through on deployed Bestie
  - the next honest step is `20.21`, not more small aggregate packet-weight tuning

### Phase 20.21. Live typed graph-state and native aggregate availability on deployed Bestie
Wave:
- Live Recall Quality
- Product Truth

Depends on:
- Phase 20.20

Purpose:
- determine why deployed Bestie still shows zero live graph/native aggregate presence on known aggregate scenarios despite active backends
- restore live typed graph-state / native aggregate availability if the missing seam is local and donor-aligned
- distinguish answer correctness from actual graph-native production truth on the live aggregate path
- re-baseline isolated live truth only if a real availability-side repair lands

Exit gate:
- the first missing live aggregate-production seam is explicitly diagnosed
- there is either:
  - one bounded repair plus one explicit live native-aggregate proof
  - or one honest blocker closeout with no fake success claim
- `aggregate_total` is no longer treated as sufficient proof by answer correctness alone
- if code changed meaningfully, one isolated post-fix live re-baseline exists

Plans:
- [x] `20.21-01-PLAN.md` — Live typed graph-state and native aggregate availability on deployed Bestie
- [x] `20.21-01-SUMMARY.md` — Live typed graph-state and native aggregate availability on deployed Bestie

Recommended next step:
- Phase 20.22 execute

Recommended agent effort:
- `high`

Execution update:
- `20.21` is execution-complete at gate.
- Summary:
  - `.planning/phases/20.21-live-typed-graph-state-and-native-aggregate-availability-on-deployed-bestie/20.21-01-SUMMARY.md`
- Real bounded win:
  - `/reset` now finalizes Brainstack using the warm cached agent rather than falling back to a cold temp agent after immediate cache eviction
  - this preserves the provider instance that actually holds `_pending_tier2_turns` for the session-end flush
- Explicit proofs:
  - live graph availability debug:
    - `reports/phase20/brainstack-20.21-live-graph-availability-debug.json`
  - isolated deployed-live reset eval:
    - `reports/phase20/brainstack-bestie-live-reset-eval-isolated.json`
- Live truth after the patch:
  - post-reset live graph state is materially present:
    - `graph_entities = 4`
    - `graph_states = 12`
  - live aggregate recall now sees graph evidence:
    - `graph candidate_count = 9`
  - focused aggregate recall returns the correct total:
    - `605 miles`
  - post-fix isolated deployed-live eval recovered to:
    - `5 / 5`
- Honest reading:
  - the missing seam was lifecycle/finalize availability, not just packet weighting or planner breadth
  - live graph-native availability is now real on deployed Bestie
  - further immediate aggregate micro-tuning would not be the best donor-first next move

### Phase 20.22. Broader deployed-live product validation and quality truth
Wave:
- Product Truth
- Live Recall Quality

Depends on:
- Phase 20.21

Purpose:
- measure broader deployed-live product quality on the now-working Brainstack/Bestie stack
- read coherence, proactive continuity, long-range recall, knowledge usability, and token/packet burden from real live scenarios
- choose the next thread from product truth instead of benchmark or aggregate momentum

Exit gate:
- there is a broader deployed-live eval beyond the narrow isolated reset harness
- the eval includes continuity, recall, and lightweight token/packet overhead truth
- one honest residual-class breakdown exists
- the next-step recommendation comes from product behavior, not technical momentum

Plans:
- [x] `20.22-01-PLAN.md` — Broader deployed-live product validation and quality truth
- [x] `20.22-01-SUMMARY.md` — Broader deployed-live product validation and quality truth

Recommended next step:
- Checkpoint current 20.21–20.22 live truth

Recommended agent effort:
- `high`

Execution note:
- the explicit pre-`20.22` audit gate is now complete
- checkpoint commits:
  - Brainstack source: `39d6430` — `chore: complete pre-20.22 Brainstack audit cleanup gate`
  - Bestie mirror: `960fef25` — `chore: sync pre-20.22 Brainstack audit cleanup`
- bounded runtime cleanup landed in owned code:
  - temporal ordering cleanup and redundant pass removal in `brainstack/executive_retrieval.py`
  - Tier-2 extractor text/non-JSON helper cleanup and bounded transcript-batch optimization in `brainstack/tier2_extractor.py`
  - Kuzu graph backend payload/rollback cleanup in `brainstack/graph_backend_kuzu.py`
  - Chroma semantic search fail-closed guard for blank query / nonpositive limit in `brainstack/corpus_backend_chroma.py`
- test-contract cleanup landed across owned Brainstack tests, including the new host import shim:
  - `tests/_host_import_shims.py`
- explicit validation truth:
  - Brainstack full own suite: `164 passed`
  - Bestie Brainstack mirror regression slice: `52 passed`
  - Brainstack own-scope `ruff`: clean
  - Brainstack own-scope `mypy --follow-imports=silent`: clean
  - Bestie Brainstack mirror own-scope `ruff`: clean
  - Bestie Brainstack mirror own-scope `mypy --follow-imports=silent`: clean
- second manual own-scope audit pass confirmed the gate and only surfaced small remaining test hygiene drift:
  - centralized repeated host import shim setup through `tests/_host_import_shims.py`
  - removed one dead import from Bestie own-scope `tests/agent/test_memory_provider.py`
  - revalidation after that second pass stayed green:
    - Brainstack changed-test slice: `64 passed`
    - Brainstack full own suite: `164 passed`
    - Bestie mirror regression slice: `52 passed`
    - Brainstack own-scope `ruff` and `mypy`: clean
- `20.22` then executed cleanly after one important harness correction.
- explicit artifacts:
  - broader deployed-live eval:
    - `reports/phase20/brainstack-20.22-broader-deployed-live-eval.json`
  - truthful chain probe:
    - `reports/phase20/brainstack-20.21-chain-probe.json`
  - initial wrong-path control:
    - `reports/phase20/brainstack-20.22-provider-direct-control.json`
- broader truth:
  - corrected matrix result on the actual deployed provider/config path: `8 / 8`
  - category read:
    - coherent continuous conversation: `1 / 1`
    - stateful continuity after reset: `2 / 2`
    - long-range recall / relation-tracking: `4 / 4`
    - larger knowledge-body recall: `1 / 1`
  - lightweight packet/token truth from the supporting truthful chain probe:
    - `matched = 6`
    - `transcript_rows = 5`
    - `graph_rows = 3`
    - `corpus_rows = 0`
    - selected excerpt token estimate: `552`
- critical correction:
  - the first red `20.22` attempt was a harness mismatch
  - it force-routed the eval onto `custom + MiniMax-M2.7`
  - the actual deployed Bestie path uses:
    - `provider: nous`
    - `model: xiaomi/mimo-v2-pro`
  - the `usage limit exceeded` artifact therefore belongs to the wrong-path control, not the final product verdict
- honest next move:
  - checkpoint current `20.21–20.22` live truth
  - if continuing immediately, prefer broader deployed-live quality/coverage validation rather than another narrow memory micro-phase
    - Bestie Brainstack mirror own-scope `ruff` and `mypy`: clean

### Phase 20.18. Low-overlap live surfacing and packet-sufficiency vs synthesis split
Wave:
- Live Recall Quality
- Product Truth

Depends on:
- Phase 20.17

Purpose:
- improve the remaining low-overlap same-principal live surfacing failures on the active degraded stack
- explicitly separate structurally under-surfaced failures from packet-sufficient but answer-weak failures
- preserve the `20.17` principal isolation and noun-`order` route gains while deciding the next honest live thread

Exit gate:
- the phase can explicitly classify the remaining live failures by residual class
- the bounded low-overlap surfacing class improves without reopening `20.17` bugs
- the next-thread recommendation is evidence-led rather than planning momentum

Plans:
- [x] `20.18-01-PLAN.md` — Low-overlap live surfacing and packet-sufficiency vs synthesis split
- [x] `20.18-01-SUMMARY.md` — Low-overlap live surfacing and packet-sufficiency vs synthesis split

Recommended next step:
- add and plan `20.19`

Recommended agent effort:
- `xhigh`

Execution update:
- `20.18` is execution-complete at gate as a bounded live-surfacing improvement phase
- the winning bounded fixes were:
  - same-principal `session_summary -> transcript` support carry-through
  - transcript-hygiene allowance for bounded same-principal support rows
  - minimal plural-query singular fallback for low-overlap lexical misses
  - backward-compatible principal filtering for legacy rows without explicit principal metadata
- source proof truth after the patch:
  - targeted phase20 slice: `7 passed`
  - broader `test_brainstack_real_world_flows.py` slice: `32 passed`, `2 failed`
  - the two broader failures remained tied to degraded graph/corpus runtime availability, not the new carry-through path
- deployed Bestie isolated live reset eval after runtime sync:
  - [brainstack-bestie-live-reset-eval-isolated.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase20/brainstack-bestie-live-reset-eval-isolated.json)
  - result: `3 / 5`
  - passes:
    - `dietary_constraint`
    - `coffee_order`
    - `gift_context`
  - fails:
    - `temporal_order`
    - `aggregate_total`
- the current honest reading is:
  - `20.18` did recover the fact-style low-overlap/product-synthesis pair on the degraded stack
  - but the remaining temporal and aggregate misses now point past degraded-stack micro-tuning
  - deployed Bestie is still running with `semantic` / `graph` degraded, so the graph/corpus capability built in `20.11–20.15` is still not live
- therefore the next follow-up should not ask:
  - “what is one more keyword/temporal heuristic?”
- the next follow-up should ask:
  - “how do we enable the donor-aligned graph/corpus runtime in deployed Bestie and then re-baseline live truth?”

### Phase 21. Brainstack-only memory ownership enforcement, communication-contract application, and memory hygiene hardening

**Goal:** Restore Brainstack-only ownership and make stored communication-contract rules reliably govern live behavior without speculative system self-explanations polluting durable memory.
**Requirements**: TBD
**Depends on:** Phase 20
**Plans:** 1 plan

Plans:
- [x] `21-01-PLAN.md` — Brainstack-only memory ownership enforcement, communication-contract application, and memory hygiene hardening
- [x] `21-01-SUMMARY.md` — Brainstack-only memory ownership enforcement, communication-contract application, and memory hygiene hardening

Recommended next step:
- checkpoint Phase 21 and, if continuing immediately, prefer broader deployed-live conversational quality / coverage validation

Recommended agent effort:
- `xhigh`

Planning note:
- this phase was created directly from a manual deployed-live audit, not benchmark pressure
- the issue is not “persona prompt weak” in isolation
- the issue is the deeper interaction between:
  - Brainstack-only ownership
  - prompt-layer precedence
  - contract-to-behavior enforcement
  - durable-memory hygiene against assistant speculation
- the phase must therefore start with architecture/runtime truth gathering before any repair

Execution update:
- `21` is execution-complete at gate.
- strongest new truths:
  - Brainstack-only ownership on the personal memory / communication-contract axis now holds on a clean temp home seeded from the deployed config/auth path
  - live `flush_memories` now requests structured JSON on the real deployed provider path instead of relying on unconstrained reasoning output
  - the active communication contract is now built from durable current truth rather than brittle fuzzy graph-only lookup
  - explicit user formatting rules that the live extractor can omit are backfilled conservatively from transcript evidence into stable communication slots
  - assistant self-explanation and file/skill/prompt-mechanics claims no longer need to be accepted as durable profile/graph truth
- explicit artifact:
  - `reports/phase21/brainstack-phase21-live-rerun-strict.json`
- strict live proof result:
  - `owns_personal_memory_axis = true`
  - persisted stable slots include:
    - `preference:response_language`
    - `preference:ai_name`
    - `preference:communication_style`
    - `preference:emoji_usage`
    - `preference:message_structure`
    - `preference:pronoun_capitalization`
    - `preference:dash_usage`
- current-state representation audit:
  - `current_state_pairs = []`
  - accepted as a non-blocking representation difference because profile rows, injected contract, and post-reset behavior still aligned on the owned contract
- adjacent-similar proof result:
  - reproduced and then closed `cronjob` as an automation-based personal-memory detour
  - reproduced and then closed `execute_code` calling secondary-memory APIs like `plur_learn`
- architectural boundary note:
  - Phase 21 proves axis-specific Brainstack ownership, not total native-feature displacement
  - native host capabilities remain legitimate outside the personal-memory axis as long as they do not become competing persistence/retrieval channels for personal-memory truth
 - broader synergy follow-up note:
   - native cron/automation now appears to have the right boundary and should not be broadly displaced
   - `session_search` likely belongs to a different capability class:
     - transcript forensics / explicit session browsing
     - not durable personal-memory ownership
 - follow-up architecture work should evaluate whether Brainstack-only mode is over-hiding `session_search`
 - separate clarity gap remains in host memory orchestration:
   - legacy built-in memory still lives directly in `run_agent.py`
   - plugin memory lives behind `MemoryManager`
   - docs/runtime layering should be reconciled before claiming a cleaner long-term synergy model

### Phase 22. Brainstack/native synergy boundary and memory orchestration clarification

**Goal:** Decide the best long-term boundary between Brainstack and native Hermes capabilities so Brainstack owns the durable personal-memory axis without over-displacing useful native features like transcript forensics or automation.
**Requirements**: TBD
**Depends on:** Phase 21
**Plans:** 1 plan

Plans:
- [x] `22-01-PLAN.md` — Brainstack/native synergy boundary and memory orchestration clarification

Recommended next step:
- checkpoint Phase `22`

Recommended agent effort:
- `xhigh`

Planning note:
- this phase exists to avoid the wrong instinct:
  - “anything memory-adjacent should be absorbed by Brainstack”
- the two strongest candidates from the post-Phase-21 architecture audit are:
  - `session_search`, which may be a valid coexistence capability rather than a competing personal-memory owner
  - the runtime/documentation drift between legacy built-in memory in `run_agent.py` and plugin memory behind `MemoryManager`
- the phase must stay anti-overengineering:
  - no broad host rewrite
  - no new giant abstraction layer
  - no blanket native-feature displacement
- refreshed guardrails for this phase:
  - donor-first
  - modularity / upstream updateability
  - truth-first
  - fail-closed on the owned axis
  - no benchmaxing
  - no overengineering
- execute should include user-facing decision checkpoints in simple language when a real architecture fork appears

Execution result:
- `22` is execution-complete at gate
- final boundary decision:
  - Brainstack owns durable personal memory
  - `session_search` is restored as bounded transcript forensics / session browsing
  - native `cronjob` remains intact outside the personal-memory axis
  - memory orchestration drift was resolved with a thin clarity fix, not a broad rewrite

Recommended next step:
- broader deployed-live conversational quality / coverage validation

### Phase 23. Broader deployed-live conversational quality and coverage validation

**Goal:** Read broader real deployed-live conversational quality and coverage honestly on top of the now-settled Brainstack/native boundary, without turning validation into stealth feature-building.
**Requirements**: TBD
**Depends on:** Phase 22
**Plans:** 1 plan

Plans:
- [x] `23-01-PLAN.md` — Broader deployed-live conversational quality and coverage validation
- [x] `23-01-SUMMARY.md` — Broader deployed-live conversational quality and coverage validation

Recommended next step:
- checkpoint Phase `23`
- then add + plan a focused follow-up for:
  - principal-scoped durable profile isolation
  - proactive continuity carry-through hardening

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is intentionally a product-truth phase, not another ownership/boundary phase
- it should measure broader real live quality against the project product targets:
  - coherent continuous conversation
  - proactive stateful continuity
  - long-range accurate recall and relation-tracking
  - usable storage of large bodies of knowledge
  - meaningful token savings
- it must stay anti-overengineering:
  - no feature-creep by default
  - no broad host cleanup
  - no benchmark-shaped drift
- only thin corrections are allowed, and only if:
  - the harness is misleading
  - or a newly surfaced blocker is clear enough that ignoring it would make the phase dishonest

Execution result:
- `23` is execution-complete at gate as a validation phase
- after correcting the harness to use the real deployed provider path, the broader live matrix landed at:
  - `9 / 10`
  - `0.9` accuracy
- category truth:
  - coherent continuous conversation: `2 / 2`
  - stateful continuity after reset: `2 / 2`
  - proactive stateful continuity: `0 / 1`
  - long-range relation-tracking: `4 / 4`
  - larger knowledge-body use: `1 / 1`
- the main residuals are now explicit:
  - proactive continuity after reset dropped dietary carry-through
  - cross-principal profile bleed exposed style/name/language durable items under unrelated principals
- important reading:
  - this does **not** falsify the Phase `22` Brainstack/native boundary
  - it points instead to:
    - principal-scope durable profile isolation
    - narrower continuity carry-through quality

Checkpoint note:
- Phase `23` should now be treated as the new broader live-quality baseline
- the settled reading after this checkpoint is:
  - the Brainstack/native boundary from Phase `22` still stands
  - broader deployed-live conversational quality is mostly healthy
  - the next justified work is not another broad validation rerun
  - it is a focused follow-up on:
    - principal-scoped durable profile isolation
    - proactive continuity carry-through hardening
- Shiba-style Tier-2 uplift remains a later capability option, not the immediate next step:
  - Brainstack already implements part of that direction
  - the current risk is that pushing extraction/rule sophistication first would widen durable profile mistakes before principal-scope isolation is repaired

### Phase 24. Principal-scoped durable profile isolation and proactive continuity carry-through hardening

**Goal:** Close the two post-Phase-23 residuals in the right order by fixing durable profile principal isolation first and then hardening proactive continuity carry-through, using shared-seam diagnosis instead of symptom patching.
**Requirements**: TBD
**Depends on:** Phase 23
**Plans:** 1 plan

Plans:
- [x] `24-01-PLAN.md` — Principal-scoped durable profile isolation and proactive continuity carry-through hardening
- [x] `24-01-SUMMARY.md` — Principal-scoped durable profile isolation and proactive continuity carry-through hardening

Recommended next step:
- checkpoint Phase `24`

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is correctness-first, not capability-first
- it must keep the settled Phase `22` boundary and the Phase `23` baseline intact unless direct evidence falsifies them
- it must not smuggle SHIBA-style Tier-2 uplift into the repair path by default
- the repair order is explicit:
  - principal-scoped durable profile isolation
  - then proactive continuity carry-through hardening
- execute should include simple-language user checkpoints only when a real architecture fork appears

Execution result:
- `24` is execution-complete at gate
- shared-seam verdict:
  - `no`
  - the two residuals were causally separate
- durable profile isolation result:
  - personal `identity` / `preference` profile rows are now principal-safe at the durable storage seam
  - scoped personal reads no longer fall back to global rows
  - Tier-2 reconcile and scoped identity canonicalization now read/write through the corrected seam
- carry-through result:
  - continuation-shaped queries now receive bounded continuation guidance and stronger transcript/continuity/graph support
  - the fix stayed selective instead of fabricating constraints
- primary artifacts:
  - [phase24-principal-bleed-canary.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase24/phase24-principal-bleed-canary.json)
  - [phase24-carry-through-deterministic.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase24/phase24-carry-through-deterministic.json)
  - [phase24-live-proactive-rerun.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase24/phase24-live-proactive-rerun.json)

Checkpoint note:
- Phase `24` should now be treated as the current correctness baseline for the post-Phase-23 residuals
- the settled reading after this checkpoint is:
  - principal-scoped durable profile isolation is closed at the durable storage / scoped lookup seam
  - proactive continuity carry-through hardening is closed at the continuation-salience / synthesis-guidance seam
  - the settled Phase `22` Brainstack/native boundary still stands

Recommended next step:
- refresh the broader deployed-live quality baseline on top of the Phase `24` truth

### Phase 25. Broader deployed-live quality baseline refresh

**Goal:** Refresh the broader deployed-live quality baseline on top of the settled Phase 24 truth, so the project has an honest post-fix product read instead of relying on the older Phase 23 baseline.
**Requirements**: TBD
**Depends on:** Phase 24
**Plans:** 2 plans

Plans:
- [x] `25-01-PLAN.md` — Broader deployed-live quality baseline refresh
- [x] `25-01-SUMMARY.md` — Broader deployed-live quality baseline refresh

Recommended next step:
- `/gsd-execute-phase 25`

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is a baseline-refresh validation phase, not another corrective phase by default
- it must preserve the settled Phase `22` boundary and the settled Phase `24` seam readings unless broader live evidence directly falsifies them
- it must explicitly compare the new broader live read against the Phase `23` baseline
- it must keep the former residual families in scope:
  - principal-scoped durable profile isolation
  - proactive continuity carry-through
- execute should prefer honest rerun classification over reactive code changes

Execution result:
- `25` is execution-complete as a baseline-refresh validation phase
- refreshed broader live baseline:
  - `9 / 10`
  - `0.9` accuracy
- baseline comparison against Phase `23`:
  - top-line score stayed flat
  - `cross_principal_profile_bleed` resolved
  - `larger_knowledge_body` improved from `acceptable_pass` to `strong_pass`
  - only `proactive_continuity_after_reset` remained
- focused variance read:
  - [brainstack-25-proactive-variance-check.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase25/brainstack-25-proactive-variance-check.json)
  - `2 / 3` pass
  - `intermittent = true`
- primary artifacts:
  - [brainstack-25-broader-deployed-live-eval.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase25/brainstack-25-broader-deployed-live-eval.json)
  - [brainstack-25-scenario-matrix.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase25/brainstack-25-scenario-matrix.json)
  - [brainstack-25-proactive-variance-check.json](/home/lauratom/Asztal/ai/atado/Brainstack/reports/phase25/brainstack-25-proactive-variance-check.json)

Checkpoint note:
- Phase `25` should now be treated as the current broader deployed-live quality baseline on top of the settled Phase `24` truth
- the settled reading after this checkpoint is:
  - the top-line broader live result remains `9 / 10`
  - `cross_principal_profile_bleed` stays closed in the broader live baseline
  - `larger_knowledge_body` stays improved from `acceptable_pass` to `strong_pass`
  - the only carried residual is narrower proactive continuity variance, not a broad correctness regression

Recommended next step:
- only consider a focused proactive continuity robustness follow-up if chasing the remaining `1 / 10`

### Phase 26. Focused proactive continuity robustness

**Goal:** Close the remaining proactive continuity residual under stricter gates by restoring the full plan frame after reset and preventing unnecessary re-ask/tool detours when memory support is already sufficient.
**Requirements**: TBD
**Depends on:** Phase 25
**Plans:** 1 plan

Plans:
- [x] `26-01-PLAN.md` — Focused proactive continuity robustness

Recommended next step:
- `/gsd-execute-phase 26`

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is a focused robustness thread, not a broad new capability phase
- it must preserve the settled Phase `22` boundary, the settled Phase `24` profile-isolation seam, and the settled Phase `25` baseline reading unless direct evidence falsifies them
- it carries four stricter mandatory filters:
  - event-frame restoration
  - no-detour proactive continuation
  - selective recall / low token waste
  - whole-path diagnosis, not memory-kernel-only blame
- execute should prefer one local seam fix over multiple reactive nudges

### Phase 27. Selective hermes-lcm host-level donor uptake

**Goal:** Adopt the small set of `hermes-lcm` host-level donor ideas that materially improve compaction auditability, lifecycle clarity, and bounded compacted-history access without introducing a second runtime, a second memory owner, or token-heavy UX regressions.
**Requirements**: TBD
**Depends on:** Phase 25
**Plans:** 1 plan

Plans:
- [x] `27-01-PLAN.md` — Selective hermes-lcm host-level donor uptake

Recommended next step:
- `/gsd-execute-phase 27`

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is a bounded donor-uptake phase, not `LCM` integration
- the target is net system improvement, not donor adoption for its own sake
- it must preserve the settled Phase `22` boundary and the settled Phase `25` baseline reading
- it must not create a second compaction runtime or a second durable truth owner
- the ordered candidate set is explicit:
  - source-window / compaction provenance
  - explicit lifecycle / frontier state
  - bounded expand/search ergonomics over compacted history
  - conditional ignored/stateless-session filtering
- execute must start with a duplicate/overlap audit against current Brainstack seams
- Brainstack is the implementation source of truth for this phase
- Bestie is only for later validation/mirroring, not parallel double-writing
- the last item is conditional only:
  - if noisy/stateless-session evidence is weak, it must be left out
- if any donor slice requires a new host plugin slot or broad host rewrite, it is out of scope for this phase
- if any donor slice creates more maintenance burden than product value, it is out of scope for this phase

Recommended next step if gate passes:
- checkpoint Phase `27`

Closeout note:
- `27` closed as selective donor uptake, not `LCM` integration
- landed:
  - bounded snapshot provenance on the existing continuity snapshot seam
  - thin Brainstack-owned lifecycle/frontier state
- explicitly deferred:
  - bounded expand/search ergonomics
  - ignored/stateless-session filtering
- Bestie was intentionally left untouched in this phase
  - later validation/mirroring should copy from Brainstack source truth, not reimplement by hand

Checkpoint note:
- `27` is now the settled baseline for selective `hermes-lcm` donor uptake
- the accepted landed scope is exactly:
  - bounded snapshot provenance
  - thin lifecycle/frontier state
- the accepted deferred scope remains:
  - bounded expand/search ergonomics
  - ignored/stateless-session filtering
- `27` does not justify donor runtime integration or a new host architecture slot
- any later Bestie work should be validation/mirroring from Brainstack source truth, not parallel implementation

## Backlog

### Phase 27.1. Bestie mirror and measured validation for selective hermes-lcm donor uptake (INSERTED)

**Goal:** Mirror the landed Phase `27` Brainstack donor slices into Bestie and prove whether they create measurable Bestie-side value instead of only cleaner internal host seams.
**Requirements**: TBD
**Depends on:** Phase 27
**Plans:** 1 plan

Plans:
- [x] `27.1-01-PLAN.md` — Bestie mirror and measured validation for selective hermes-lcm donor uptake

Recommended next step:
- `/gsd-execute-phase 27.1`

Recommended agent effort:
- `xhigh`

Planning note:
- this is a narrow mirror-and-proof phase, not a new donor phase
- only the landed Phase `27` slices are in scope:
  - bounded snapshot provenance
  - thin lifecycle/frontier state
- Bestie is the validation/mirror target only
- success requires measured proof, not just correct wiring
- acceptable final verdicts are explicit:
  - measured win
  - correct mirror, no proven product lift yet
  - not worth keeping

Closeout note:
- `27.1` closed with a measured but narrow win
- mirrored into Bestie:
  - bounded snapshot provenance
  - thin lifecycle/frontier state
- measured result:
  - auditability / diagnostics improved
  - ordinary-turn token surface stayed neutral in the measured scenario
  - retrieval usefulness uplift was not proven

Recommended next step if gate passes:
- checkpoint Phase `27.1`

Checkpoint note:
- `27.1` is now the settled Bestie mirror baseline for the landed Phase `27` donor slices
- accepted mirrored scope:
  - bounded snapshot provenance
  - thin lifecycle/frontier state
- measured settled reading:
  - auditability / diagnostics improved
  - ordinary-turn token surface stayed neutral in the measured scenario
  - retrieval usefulness uplift remains unproven
- this checkpoint proves correct mirroring and a narrow operational win, not a broader retrieval-quality lift

### Phase 28. Targeted upstream donor delta audit and selective refresh

**Goal:** Audit the latest upstream Hindsight, MemPalace, and Graphiti deltas against the settled Brainstack baseline, then adopt only the thin slices with real product value and bounded maintenance cost.
**Requirements**: TBD
**Depends on:** Phase 27.1
**Plans:** 1 plan

Plans:
- [x] `28-01-PLAN.md` — Targeted upstream donor delta audit and selective refresh

Recommended next step:
- `/gsd-execute-phase 28`

Recommended agent effort:
- `xhigh`

Planning note:
- this is a selective latest-delta audit phase, not a blanket donor sync
- it must preserve the settled Phase `22`, `24`, `25`, `27`, and `27.1` readings
- Brainstack remains the source-of-truth implementation repo
- Bestie is out of scope unless a later mirror phase is explicitly opened
- current donor-reading at plan time is:
  - Hindsight:
    - highest immediate candidate
    - likely around bounded retrieval-budget discipline
  - MemPalace:
    - likely audit-only unless backend-boundary leakage is found
  - Graphiti:
    - explicit no-op unless the audit finds a concrete runtime-ROI delta
- this phase is allowed to close with:
  - selective win
  - audit-only no-op
  - explicit defer
- if a donor slice requires broad rewrite, new runtime dependencies, or more config surface than value, it is out of scope
- if a donor slice only duplicates local behavior, it must not land

### Phase 28.1. Bounded RTK sidecar runtime wiring and value audit (INSERTED)

**Goal:** Prove whether the local RTK sidecar deserves correct runtime wiring and a very small preprocessing uplift, or whether it should remain a thin no-op budget layer instead of growing into a second RTK system.
**Requirements**: TBD
**Depends on:** Phase 28
**Plans:** 1 plan

Plans:
- [x] `28.1-01-PLAN.md` — Bounded RTK sidecar runtime wiring and value audit

Recommended next step:
- `/gsd-execute-phase 28.1`

Recommended agent effort:
- `high`

Planning note:
- this is a bounded sidecar audit phase, not a donor-port phase
- latest upstream `rtk` is treated as design input only:
  - output filtering
  - grouping
  - truncation
  - deduplication
- the local `rtk_sidecar` must remain a thin Hermes-owned layer:
  - config
  - telemetry
  - optional tiny pre-normalization
- `tools/tool_result_storage.py` remains the owner of:
  - persistence
  - truncation fallback
  - turn-budget enforcement behavior
- the phase must first settle runtime truth:
  - `hermes-agent-latest` already carries live sidecar wiring
  - `hermes-final` must not be patched blindly until the source-of-truth and installer path are confirmed clean
- acceptable outcomes are explicit:
  - wiring-only correction
  - wiring plus tiny measurable uplift
  - explicit no-op / do not adopt
- out of scope:
  - command-specific filter forests
  - a second RTK implemented inside Hermes
  - broad heuristics that risk structured tool-output correctness

### Phase 29. Live communication-contract recall and post-reset durability forensics

**Goal:** Explain why the deployed Bestie runtime still drops Humanizer / communication-contract rules after session reset while retaining identity and other personal facts, then isolate the real broken seam before any fix is attempted.
**Requirements**: TBD
**Depends on:** Phase 21, Phase 24, Phase 27.1
**Plans:** 1 plan

Plans:
- [x] `29-01-PLAN.md` — Live communication-contract recall and post-reset durability forensics

Recommended next step:
- direct deployed-path UAT for the repaired reset behavior
- then resume the paused donor-side threads only after that acceptance pass

Recommended agent effort:
- `xhigh`

Planning note:
- this is a correctness-first forensic phase, not a donor-update phase
- new live evidence has falsified the settled reading that communication-contract durability is already holding after reset
- the phase must distinguish five possibilities instead of assuming a prompt weakness:
  - the Humanizer-style rules never entered durable Brainstack state correctly
  - they were written durably but not retrieved
  - they were retrieved but not assembled into the active communication contract
  - they were assembled but weakly applied or overridden by host defaults
  - the deployed reset/runtime path is stale and bypasses valid Brainstack state
- identity recall and style-rule recall must be traced as separate outputs of the same personal-memory axis
- out of scope:
  - persona-file bandaids
  - skill-file or local-file memory substitutes
  - net/local search detours as a substitute for durable Brainstack recall
  - donor work unless the forensic trace proves a donor seam is the real cause

Execution result:
- `29` is execution-complete at gate locally
- final seam verdict:
  - primary seam:
    - legacy unscoped principal-scoped communication preferences were being dropped at the scoped retrieval / active-contract boundary
  - secondary correctness bug:
    - Tier-2 worker and session-end flush could fail before promotion because the Tier-2 caller passed an unsupported direct `response_format` keyword
- shipped repair:
  - deterministic open-time backfill for legacy unscoped principal-scoped profile rows when transcript evidence resolves to one unique principal scope
  - Tier-2 caller fix via `extra_body={\"response_format\": ...}`
- deployed-path proof:
  - live docker runtime now shows scoped profile keys for the affected principal
  - a fresh deployed-path `AIAgent._build_system_prompt()` now contains the Bestie naming line, newline rule, `Én / Te / Ő` capitalization rule, Hungarian rule, and the broader Humanizer contract lines
  - isolated runtime provider proof shows `on_session_end()` can again land a scoped preference row end-to-end
- ruled out:
  - total absence of durable communication data
  - pure prompt weakness
  - pure application-only override after a correct contract was already present
- residual note:
  - principal-model drift between the older `default/hermes/numeric-id` scope and the newer naming shape remains adjacent work, but it was not the minimum repair surface for this regression

### Phase 29.2. Practical logistics memory capture and reminder boundary audit (INSERTED)

**Goal:** [Urgent work - to be planned]
**Requirements**: TBD
**Depends on:** Phase 29
**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd-plan-phase 29.2 to break down)

### Phase 29.1. Canonical communication contract and durable identity capture hardening (INSERTED)

**Goal:** Convert the repaired communication-memory lane into one canonical durable contract shape and restore durable capture of explicit identity facts such as age, without falling back to brittle runtime guardrails.
**Requirements**: TBD
**Depends on:** Phase 29
**Plans:** 1 plan

Plans:
- [x] `29.1-01-PLAN.md` — Canonical communication contract and durable identity capture hardening
- [x] `29.1-01-SUMMARY.md` — Canonical communication contract and durable identity capture hardening

Recommended next step:
- `/gsd-execute-phase 29.2`

Recommended agent effort:
- `high`

Planning note:
- this is a durable-data-shape hardening phase, not a runtime-obedience or prompt-strength phase
- new live evidence now splits the remaining gap into two proven issues:
  - communication rules survive durably, but in a fragmented legacy-plus-canonical profile shape
  - explicit age survives through transcript fallback, but not as a durable `identity:age` row
- the phase must preserve Brainstack as the single owner of personal memory on this axis
- the phase must not solve this with:
  - persona or skill files
  - prompt stuffing
  - brittle output guardrails
  - a rollback to broad handwritten Tier-1 profile inference
- acceptable outcomes are bounded:
  - one canonical communication-contract slot family and projection shape
  - one deterministic explicit-identity capture path for age
  - bounded migration/backfill of legacy fragmented rows
  - or an explicit no-go verdict for any part that adds more maintenance cost than value
- execution status:
  - closed
- execute verdict:
  - the final repair stayed inside Brainstack-owned seams:
    - shared contract helper
    - deterministic Tier-2 explicit-age fallback
    - versioned one-shot compatibility migrations
  - deployed proof now includes:
    - live `identity:age`
    - both migration markers present
    - clean communication-contract projection in the running container

### Phase 29.2. Practical logistics memory capture and reminder boundary audit (INSERTED)

**Goal:** Determine the correct durable shelf and handoff model for user logistics facts such as addresses, appointments, one-off reminders, and short practical todo items, then close the gap where they currently survive only in transcript/continuity.
**Requirements**: TBD
**Depends on:** Phase 29, Phase 29.1
**Plans:** 1 plan

Plans:
- [x] `29.2-01-PLAN.md` — Practical logistics memory capture and reminder boundary audit
- [x] `29.2-01-SUMMARY.md` — Practical logistics memory capture and reminder boundary audit
- [x] `29.2-UAT.md` — Combined deployed-path verify for Phase 29.1 + 29.2

Recommended next step:
- move on from the Phase `29` closure work; combined deployed-path UAT is complete in `29.2-UAT.md`

Recommended agent effort:
- `high`

Planning note:
- this is a memory-boundary audit phase, not a blind "write all logistics into profile" phase
- live evidence shows the current system remembered the massage address and reminder discussion only through:
  - `transcript_entries`
  - `continuity_events`
- the same evidence did **not** appear in:
  - `profile_items`
  - `graph` shelves
- the phase must therefore decide the right owner for each class:
  - stable place/contact facts
  - scheduled appointment instances
  - reminder handoff state
  - transient today's todo items
- the phase must not solve this by:
  - stuffing all practical facts into profile rows
  - keeping everything only in continuity
  - creating a second reminder truth owner outside the existing reminder path

### Phase 29.3. Full Humanizer contract durability and style-pack recall forensics (INSERTED)

**Goal:** Determine why Brainstack preserves only a short active communication contract while dropping the full 29-rule Humanizer contract from durable recall, then identify the architecturally correct durable model before any fix is attempted.
**Requirements**: TBD
**Depends on:** Phase 29, Phase 29.1, Phase 29.2
**Plans:** 1 plan

Plans:
- [x] `29.3-01-PLAN.md` — Full Humanizer contract durability and style-pack recall forensics
- [x] `29.3-01-SUMMARY.md` — Zero-heuristic style-contract lane implementation summary
- [x] `29.3-UAT.md` — Live verification for explicit style recall vs ordinary-turn exclusion

Recommended next step:
- phase `29` closure work is complete; next work should be a separate follow-up, not more 29.3 redesign

Recommended agent effort:
- `xhigh`

Planning note:
- the rejected heuristic 29.3 attempt was reverted and replaced
- final verdict:
  - compact communication slots remain the ordinary-turn lane
  - one canonical principal-scoped `preference:style_contract` now owns detailed Humanizer recall
  - explicit style/rules recall goes through the existing model-backed routing seam
  - ordinary turns exclude the long-form style contract
  - legacy corpus-backed style artifacts are migrated once into the canonical profile lane and retired
  - installer hardening now sets `auxiliary.flush_memories.provider: main` so Tier-2 writes do not depend on a separate auxiliary provider chain
- out of scope:
  - hardcoding 29 separate style rules into runtime prompt logic
  - output-policing guardrails
  - persona-file, skill-file, or local-file substitutes
  - heuristics that guess style packs from loose wording without a stable data model
    - malformed prefixed address demoted to historical state
    - no `Fodrász / Bank` durable pollution
  - combined verify verdict:
    - 6 / 6 checks passed
    - the former direct-age residual is now closed:
      - direct `Hány éves vagyok?` queries resolve to `profile_slot_targets = ('identity:age',)`
      - the deployed packet returns the durable `identity:age` row as the first profile item

### Phase 29.4. Oracle regression runner repair and pre-forensics gate (INSERTED)

**Goal:** Restore a trustworthy bounded oracle regression path before any new 27-rule recall forensics, so the next investigation can prove whether recent Brainstack changes regressed earlier LongMemEval-backed proof instead of guessing.
**Requirements**: TBD
**Depends on:** Phase 20.15, Phase 29.3
**Plans:** 1 plan

Plans:
- [ ] `29.4-01-PLAN.md` — Oracle regression runner repair and pre-forensics gate

Recommended next step:
- execute `29.4` before any new product-path recall fix work

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is not a new Brainstack memory feature
- it is a correctness-first gate on the benchmark/oracle harness itself
- success means:
  - the bounded oracle regression check runs again on the intended retrieval-only path
  - the runner no longer forces remote API wiring where the proof mode should not need it
  - the project regains a trustworthy answer to the question:
    - did the recent `29.1` / `29.2` / `29.3` changes regress earlier proof?
- only after that gate passes may a new phase localize what still breaks in the 27-rule recall behavior

Status note:
- closed locally with a completed bounded `oracle 60` retrieval-only rerun
- no broad regression emergency was found
- the next phase narrows to live style-contract ingest fidelity, not runner health

### Phase 29.5. Lossless style-contract ingest and live recall fidelity (INSERTED)

**Goal:** Close the remaining live `27`-rule recall gap by proving and repairing the exact blocker between the already-stored detailed style contract and the explicit post-reset recall path, while preserving compact ordinary turns and setting up the bridge to an always-on compiled behavior policy.
**Requirements**: TBD
**Depends on:** Phase 29.3, Phase 29.4
**Plans:** 1 plan

Plans:
- [ ] `29.5-01-PLAN.md` — lossless style-contract ingest and live recall fidelity

Recommended next step:
- execute `29.5`

Recommended agent effort:
- `xhigh`

Planning note:
- `29.4` already proved the bounded oracle gate is healthy again
- the newer live evidence is sharper than the original `29.5` framing:
  - the detailed canonical `preference:style_contract` row can exist with the full contract
  - the remaining live failure path has included:
    - route-hint/runtime dependency failure that dropped explicit style questions back to `fact`
    - ordinary-turn exclusion by design
    - absence of an always-on compiled behavior policy for obedience
- success means:
  - explicit detailed recall after reset reliably reaches the canonical detailed lane in the deployed runtime
  - the canonical detailed row remains full and current
  - the final `29.5` summary names exactly which remaining behavior gaps belong to:
    - route/runtime parity
    - render/projection
    - or the larger always-on policy architecture handoff to `29.6+`
  - ordinary turns stay compact and token-disciplined

### Phase 29.6. Always-on compiled behavior contract and raw archival split (INSERTED)

**Goal:** Split user communication policy into two first-class Brainstack-owned layers: one raw archival contract for exact recall and one compiled always-on behavior contract for every ordinary turn.
**Requirements**: TBD
**Depends on:** Phase 29.5
**Plans:** 1 plan

Plans:
- [ ] `29.6-01-PLAN.md` — Always-on compiled behavior contract and raw archival split

Recommended next step:
- execute `29.6` immediately after `29.5` because this is the first architecturally correct answer to the external review's strongest criticism

Recommended agent effort:
- `xhigh`

Planning note:
- this phase accepts the validated insight that explicit user behavior rules are not just recallable memory items
- it must create:
  - one archival durable source of truth for the literal taught contract
  - one compiled machine-facing policy object for ordinary-turn obedience
  - one and only one ordinary-turn runtime authority for reply behavior once compiled policy is active
- it must not solve the problem by:
  - stuffing long-form raw contract text into every prompt
  - adding prompt-policing guardrails
  - creating a second shadow owner outside Brainstack
  - leaving legacy compact communication slots as parallel runtime authorities

### Phase 29.7. Synchronous policy teaching and immediate activation (INSERTED)

**Goal:** Make explicit policy teaching a synchronous write-through path so that when the user teaches or edits behavior rules, Brainstack persists and activates them before the next answer rather than waiting on delayed Tier-2 batching.
**Requirements**: TBD
**Depends on:** Phase 29.6
**Plans:** 1 plan

Plans:
- [ ] `29.7-01-PLAN.md` — Synchronous policy teaching and immediate activation

Recommended next step:
- execute `29.7` after the dual-layer policy model exists in `29.6`

Recommended agent effort:
- `xhigh`

Planning note:
- this phase keeps Tier-2 as enrichment, not as the first owner of explicit communication policy
- it should harden the user-facing contract:
  - teach now
  - persist now
  - activate now
- activation must be transactional and fail-closed
  - old active policy stays active if compile/validation fails
  - no silent partial activation
- it must not regress donor-first boundaries or create a handwritten Tier-1 semantic guessing engine

### Phase 29.8. Communication policy ontology and compiler expansion (INSERTED)

**Goal:** Expand the current tiny compact communication slot family into a richer first-class behavior ontology that can compile nuanced user policy without blowing up ordinary-turn token usage.
**Requirements**: TBD
**Depends on:** Phase 29.6, Phase 29.7
**Plans:** 1 plan

Plans:
- [ ] `29.8-01-PLAN.md` — Communication policy ontology and compiler expansion

Recommended next step:
- execute `29.8` once the raw/compiled split and sync activation path both exist

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is where valid parts of the 27-rule critique become concrete schema work
- it should decide which policy dimensions deserve first-class compiled representation
- it must guarantee that no taught rule disappears silently during compilation
- every taught rule must receive a named coverage outcome
- it must preserve:
  - token discipline
  - multimodal readiness
  - donor-first updateability
- it must not become a giant heuristic rule table

### Phase 29.9. End-to-end obedience and behavioral regression harness (INSERTED)

**Goal:** Add product-facing acceptance coverage that verifies actual answers obey the active behavior policy across ordinary prompts, instead of treating retrieval packet health as sufficient proof.
**Requirements**: TBD
**Depends on:** Phase 29.7, Phase 29.8
**Plans:** 1 plan

Plans:
- [ ] `29.9-01-PLAN.md` — End-to-end obedience and behavioral regression harness

Recommended next step:
- execute `29.9` after compiled policy and sync activation are both real

Recommended agent effort:
- `high`

Planning note:
- this phase converts the strongest external review criticism into an explicit product gate
- it should verify things like:
  - punctuation policy
  - newline policy
  - emoji/dash rules
  - formatting/tone constraints
- it must include:
  - ordinary prompts that never mention the rules
  - a real Hungarian long-form rule-pack fixture
  - no-dual-owner scenarios
  - principal-isolation scenarios
- it must not collapse into benchmark-shaped overfitting or brittle output-policing hacks

### Phase 29.10. Behavior-policy observability, correction, and runtime parity (INSERTED)

**Goal:** Make active behavior policy inspectable and deployment-safe through per-turn traceability, bounded correction flow, and doctor/runtime parity gates.
**Requirements**: TBD
**Depends on:** Phase 29.6, Phase 29.7, Phase 29.8, Phase 29.9
**Plans:** 1 plan

Plans:
- [ ] `29.10-01-PLAN.md` — Behavior-policy observability, correction, and runtime parity

Recommended next step:
- execute `29.10` after compiled policy, sync activation, and answer-level obedience are real

Recommended agent effort:
- `high`

Planning note:
- this phase closes the productization gap left by pure architecture work
- it must provide:
  - per-turn behavior-policy trace
  - active/raw/coverage inspection surface
  - bounded correction/supersession flow
  - doctor/install/live parity checks
- it must not become a giant admin subsystem or noisy always-on debug layer

### Phase 30.0. Second-brain always-on and proactive-agent operating model (INSERTED)

**Goal:** Extend the same raw-vs-compiled architecture beyond communication style so Brainstack can become a genuinely always-on second-brain kernel for durable user context, routines, places, contacts, and proactive agent behavior.
**Requirements**: TBD
**Depends on:** Phase 29.6, Phase 29.7, Phase 29.9
**Plans:** 1 plan

Plans:
- [ ] `30.0-01-PLAN.md` — Second-brain always-on and proactive-agent operating model

Recommended next step:
- execute `30.0` only after behavior policy itself is deterministic and trusted

Recommended agent effort:
- `xhigh`

Planning note:
- this phase deliberately broadens scope beyond the 27-rule issue
- it captures the valid long-range product aim:
  - second-brain always-on
  - proactive agent continuity
  - durable but bounded personal operating context
- it must formalize an operating-context matrix, not just a vague proactive concept
- it must still preserve single-owner boundaries and not invade Chron or create shadow subsystems

### Phase 30.1. Offline long-form knowledge and graph pipeline separation (INSERTED)

**Goal:** Separate large-scale document / book knowledge ingestion from chat-memory behavior policy so Brainstack can grow toward a stronger knowledge graph without corrupting the chat-time memory kernel.
**Requirements**: TBD
**Depends on:** Phase 29.8, Phase 30.0
**Plans:** 1 plan

Plans:
- [ ] `30.1-01-PLAN.md` — Offline long-form knowledge and graph pipeline separation

Recommended next step:
- keep this phase as the roadmap-level destination for the valid KG critique, not as an excuse to derail the current behavior-policy recovery

Recommended agent effort:
- `xhigh`

Planning note:
- this phase preserves the useful part of the external review's KG warning
- it should treat:
  - chat-time memory
  - long-form document memory
  - offline graph construction
  - evidence/provenance and temporal merge
  as related but separate concerns
- it must define a bounded evidence-backed pilot shape, not just an abstract future KG
- it is intentionally not the immediate next execution cut

### Phase 30.2. Live residual recovery for task continuity recall, style-contract fidelity, and correction semantics (INSERTED)

**Goal:** Close the three live Discord residual classes proven after `v1.0.4`: cross-session task recall failure, lossy canonical style-contract storage, and missing same-session correction-to-policy semantics.
**Requirements**: TBD
**Depends on:** Phase 29.7, Phase 29.8, Phase 29.10, Phase 30.0
**Plans:** 1 plan

Plans:
- [ ] `30.2-01-PLAN.md` — Live residual recovery for task continuity recall, style-contract fidelity, and correction semantics

Recommended next step:
- lock the residual classes as separate contracts before touching product code again; do not treat this as a single prompt-strength bug

Recommended agent effort:
- `xhigh`

Planning note:
- the task residual is not just “memory missing”
- live evidence already shows:
  - task continuity can be written
  - but reset-era retrieval can still miss it
- the style residual is not just “model ignored the rule”
- live evidence already shows:
  - the canonical scoped `style_contract` row itself can still be `tier2_llm`-derived and lossy
- the correction residual is not just “the user reminded it”
- live evidence already shows:
  - ordinary chat correction is not automatically the same thing as explicit behavior-policy correction
- this phase must preserve donor-first boundaries:
  - no shadow task manager
  - no regex output-policing bandaid
  - no broad redesign disguised as a residual fix
- it must also close the over-optimistic behavior-policy contract:
  - compiled coverage cannot claim effective ordinary-turn enforcement for rules omitted by projection budget
  - plain-chat structured teaching must become pre-answer activation, not just explicit memory-write activation

### Phase 30.3. Host/runtime compliance and truthful memory operations (INSERTED)

**Goal:** Add the host/runtime quality gates that turn Brainstack from “policy present in prompt” into truthful, inspectable, hard-constraint-aware behavior at the final answer and memory-operation layers.
**Requirements**: TBD
**Depends on:** Phase 30.2
**Plans:** 1 plan

Plans:
- [ ] `30.3-01-PLAN.md` — Host/runtime compliance and truthful memory operations

Recommended next step:
- execute this immediately after `30.2` so write acknowledgements, reset boundaries, and final-answer hard constraints stop drifting apart from the memory layer

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is where the pro-agent runtime warnings belong
- it should cover:
  - hard surface validation for mechanical reply constraints
  - truthful write receipts
  - reset-time durable write barriers
  - truthful null-result semantics
  - tool-routing and lookup-order corrections for task-like asks
- this phase is intentionally not the task-truth-class decision itself
- it hardens the host/runtime contract around whatever truth classes already exist

### Phase 30.4. Task and commitment truth-class resolution (INSERTED)

**Goal:** Resolve the task / commitment memory gap with a first-class, durable, inspectable contract: either Brainstack-owned task truth or a real external-owner bridge with durable pointers and retrieval semantics.
**Requirements**: TBD
**Depends on:** Phase 30.2, Phase 30.3
**Plans:** 1 plan

Plans:
- [ ] `30.4-01-PLAN.md` — Task and commitment truth-class resolution

Recommended next step:
- only execute this after `30.2` and `30.3` make the current boundary and failure modes explicit; then choose the stronger architecture on evidence, not guesswork

Recommended agent effort:
- `xhigh`

Planning note:
- this is not a vague backlog parking lot
- it is a concrete product-quality phase because the current system can talk like a second brain while lacking a real task truth contract
- accepted outcomes may include:
  - a first-class Brainstack task/commitment owner
  - or a real external-owner bridge with durable pointers, receipts, and retrieval
- rejected outcomes:
  - pretending continuity or session search is sufficient task truth
  - false “I saved it” acknowledgements without committed records

### Phase 30.5. Canonical multi-message operating-rule convergence and reset-safe durability (INSERTED)

**Goal:** Make long operating-rule teaching and correction survive real chat shape: multiple user messages, assistant restatements, explicit corrections, and session reset must converge into one canonical, durable operating-rule contract instead of fragmenting into session-only reinforcement or partial recall.
**Requirements**: TBD
**Depends on:** Phase 30.2, Phase 30.3, Phase 30.4
**Plans:** 1 plan

Plans:
- [ ] `30.5-01-PLAN.md` — Canonical multi-message operating-rule convergence and reset-safe durability

Recommended next step:
- execute this before any broader capability expansion, because the current user-facing failure is no longer “missing memory” in the abstract; it is broken canonicalization and reset-unsound operating-rule updates

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is about durable operating-rule truth, not prompt cosmetics
- accepted outcomes:
  - multi-message teaching converges into one canonical raw contract revision
  - explicit user corrections become durable rule updates when the user intent is persistent operating-rule change
  - assistant paraphrase is never treated as the canonical source of truth
  - reset after a confirmed rule update still preserves the canonical revision
- rejected outcomes:
  - session-only reinforcement presented as durable change
  - “I updated it” acknowledgements without a committed canonical revision
  - treating an assistant-echoed rule list as if it were user-authored canonical truth

### Phase 30.6. Graph-truth ingest hardening with first-class typed evidence boundary (INSERTED)

**Goal:** Make graph-truth writes pass through a first-class typed evidence boundary so entities, relations, and temporal state are no longer created directly from raw text parsing on the live path.
**Requirements**: TBD
**Depends on:** Phase 30.5
**Plans:** 1 plan

Plans:
- [ ] `30.6-01-PLAN.md` — Graph-truth ingest hardening with first-class typed evidence boundary

Recommended next step:
- execute this next, because after `30.5` the remaining architecturally similar authority gap now sits in graph truth: raw text still reaches the graph shelf too directly, while the product promise expects bounded, inspectable entity/relation/temporal truth

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is about graph-truth authority hardening, not a broad knowledge-graph expansion
- accepted outcomes:
  - graph-truth writes require a first-class typed fact/evidence envelope
  - raw text may remain in transcript and corpus shelves, but it no longer enters graph truth as authority
  - Tier-1 graph extraction becomes conservative and typed instead of direct raw-text graph mutation
  - the boundary is shaped for later multimodal evidence without requiring a broad multimodal rebuild in this phase
- rejected outcomes:
  - adding more language-specific regex farms to the current raw-text graph ingest path
  - donor-hetti KG platform growth disguised as ingest hardening
  - making corpus or transcript storage typed just because graph truth now is
  - degrade-open graph writes when typed evidence is missing

### Phase 31. Post-30.6 regression forensics and cross-agent root-cause convergence (INSERTED)

**Goal:** Freeze the accepted root-cause model for the post-`30.5`/`30.6` deterioration so fixes target the real breakpoints instead of vague “memory got worse” narratives.
**Requirements**: TBD
**Depends on:** Phase 30.5, Phase 30.6
**Plans:** 1 plan

Plans:
- [ ] `31-01-PLAN.md` — Post-30.6 regression forensics and cross-agent root-cause convergence

Recommended next step:
- execute this before the hotfix, because the current live failure mixes three different classes:
  - bad canonical behavior-contract revision becoming active
  - missing multi-message convergence for explicit rule teaching
  - host tool blocking wired only on part of the tool-execution path

Recommended agent effort:
- `xhigh`

Planning note:
- this is a forensics-and-convergence phase, not a cosmetic cleanup
- accepted outcomes:
  - one evidence-backed root-cause reading that reconciles live Discord behavior, runtime session traces, and current code seams
  - explicit confirmation of whether the active canonical contract is partial, who wrote it, and why it superseded better truth
  - explicit confirmation of whether Brainstack-only tool blocking is uniform across sequential and concurrent execution paths
  - explicit confirmation of whether `session_search` is still being used as a personal-memory fallback in practice
- rejected outcomes:
  - hand-wavy “the model was confused” explanations
  - blaming `30.5` in the abstract without tracing the concrete authority/admission/runtime seams
  - bundling fixes into this phase before the accepted root-cause model is frozen

### Phase 32. Canonical contract protection, multi-message convergence, and sequential-path tool blocking hotfix (INSERTED)

**Goal:** Hotfix the concrete seams identified by Phase `31` so canonical operating-rule truth can no longer degrade into partial Tier-2 revisions, multi-message rule teaching converges correctly, and Brainstack-only tool blocking applies on every live tool path.
**Requirements**: TBD
**Depends on:** Phase 31
**Plans:** 1 plan

Plans:
- [ ] `32-01-PLAN.md` — Canonical contract protection, multi-message convergence, and sequential-path tool blocking hotfix

Recommended next step:
- execute this immediately after `31`, because the current system can feel worse than before precisely when the active behavior-contract truth is wrong and the host still allows side-memory tool escapes

Recommended agent effort:
- `xhigh`

Planning note:
- this is a production hotfix phase, not another abstract behavior-memory refactor
- accepted outcomes:
  - weaker or partial `tier2_llm` style-contract writes cannot supersede stronger explicit user-authored canonical contract revisions
  - explicit multi-message rule teaching converges into one canonical contract revision instead of fragmenting across turns
  - Brainstack-only tool blocking applies in both sequential and concurrent tool execution paths
  - the style-contract recall lane stops falling back to `session_search` as if it were a personal-memory owner
- rejected outcomes:
  - keeping the current “guidance only” posture where side tools remain callable in one execution mode
  - letting partial Tier-2 contracts stay authoritative because they compile cleanly
  - session-local reinforcement or assistant echo being treated as if it were durable committed rule truth

### Phase 33. Personal-scope hardening, correction-patch capture, obedience convergence, and personal-retrieval depth (INSERTED)

**Goal:** Strengthen Brainstack as a general second-brain / continuous agent after the `32` hotfix by hardening personal scope continuity, making short explicit user corrections patch canonical truth, narrowing the gap between canonical personal truth and ordinary-turn behavior, and stopping self-starvation on personal/preference recall.
**Requirements**: TBD
**Depends on:** Phase 32
**Plans:** 1 plan

Plans:
- [ ] `33-01-PLAN.md` — Personal-scope hardening, correction-patch capture, obedience convergence, and personal-retrieval depth

Recommended next step:
- plan and execute this after `32` verify, because this is the next broader kernel-quality phase, not part of the immediate hotfix

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is intentionally broader than `32`, but it is still one coherent second-brain quality phase rather than a mixed backlog bucket
- its core workstreams are exactly:
  - personal-scope hardening / fallback
  - short explicit user-correction to canonical patch capture
  - canonical personal truth to ordinary-turn obedience convergence
  - personal/preference retrieval starvation reduction
- accepted outcomes:
  - personal behavior/preference truth does not become brittle just because `agent_workspace` or adjacent runtime identity surfaces drift
  - short, explicit user corrections can become durable canonical patches without requiring a full rule-pack resend
  - ordinary-turn behavior uses authoritative personal truth more reliably instead of leaving too much obedience as prompt-only hope
  - personal/preference/self-model questions no longer starve the system of the very channels needed for second-brain continuity
- rejected outcomes:
  - turning this into another special-case `29`-rule rescue phase
  - adding more marker farms, keyword gates, or benchmark-shaped hacks
  - broad KG redesign, broad multimodal rebuild, or unrelated host/runtime cleanup smuggled into this phase
  - solving continuity drift with duplicate owners or local shadow memory systems

### Phase 34. Brainstack role split, injection de-escalation, and LLM-synergy recovery (INSERTED)

**Goal:** Re-balance Brainstack so it strengthens the LLM as a second-brain / continuity kernel instead of competing with it as a broad behavior-governance layer. Preserve durable truth, continuity, and explicit hard invariants, while de-escalating ordinary-turn steering that overloads or conflicts with live chat reasoning.
**Requirements**: TBD
**Depends on:** Phase 33
**Plans:** 1 plan

Plans:
- [ ] `34-01-PLAN.md` — Brainstack role split, injection de-escalation, and LLM-synergy recovery

Recommended next step:
- plan and execute this after `33`, because the newly surfaced product problem is no longer just correctness drift; it is that Brainstack can become non-synergistic with the LLM when too much behavior shaping is injected into ordinary turns

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is a strategic kernel-shape correction, not another rule-pack rescue
- it must explicitly leave room for the user to be only partially right:
  - preserve the parts of Brainstack that measurably improve second-brain continuity
  - reduce only the parts that turn memory into a competing prompt-governance harness
- accepted outcomes:
  - Brainstack has a cleaner role split between:
    - archival / exact-recall behavior memory
    - narrow ordinary-turn invariants
    - factual continuity / task / graph / identity support
  - ordinary-turn memory injection becomes less intrusive and more synergistic with live conversation context
  - local chat reasoning regains primacy for immediate wording and social flow while Brainstack continues to supply durable truth and continuity
  - the runtime no longer needs to juggle large behavior-contract payloads as if they were always-on turn governance
- rejected outcomes:
  - throwing away Brainstack's second-brain role because behavior control was overextended
  - solving the problem with yet another layer of special-case behavior heuristics
  - keeping the current broad behavior-steering model just because its storage / trace story improved
  - replacing ordinary-turn synergy questions with benchmark-shaped prompt stuffing or stronger contract micromanagement

### Phase 35. First-class operating truth, owner-first retrieval, and operating-substrate maturation (INSERTED)

**Goal:** Strengthen Brainstack where a second brain should actually be strongest: the user’s active work, open decisions, current commitments, next steps, and external-owner links. Mature the operating substrate so the system knows more about what is happening in the user’s world and work, not just how it should answer.
**Requirements**: TBD
**Depends on:** Phase 34
**Plans:** 1 plan

Plans:
- [ ] `35-01-PLAN.md` — First-class operating truth, owner-first retrieval, and operating-substrate maturation

Recommended next step:
- plan this after `34`, because once Brainstack stops over-governing ordinary turns, the next highest-value move is to strengthen the operating world model it should have been contributing in the first place

Recommended agent effort:
- `xhigh`

Planning note:
- this phase captures the valid zoomed-out concern that Brainstack has become relatively stronger at behavior/answer truth than at operating/world truth
- it is not another style or compliance phase
- accepted outcomes:
  - the operating context stops being mostly a derived continuity summary and gains a small first-class operating-truth layer
  - the system can represent and surface bounded records such as:
    - active work
    - open decision
    - current commitment
    - next step
    - external owner pointer
  - retrieval moves closer to owner-first logic:
    - decide the likely authoritative truth owner first
    - then use surface cues mainly for budget shaping instead of owner selection
  - the truth classes become less like isolated mini-systems and more like a coherent operating substrate
  - the typed evidence direction stays narrow and honest rather than exploding into a broad ontology project
- rejected outcomes:
  - more behavior-heavy work while the operating layer stays weak
  - broad KG overbuild or ontology sprawl
  - reintroducing cue-farm routing as the main arbiter of what truth owner is even consulted
  - treating every chat summary as if it were a first-class operating record

### Phase 36. Memory-context collapse, owner arbitration, and low-noise working-memory assembly (INSERTED)

**Goal:** Finish the part that `34` and `35` still leave open: make the turn-time memory packet coherent, deduplicated, and owner-driven so Brainstack helps the LLM with durable truth instead of competing with it through layered meta-blocks, overlapping shelves, and duplicated evidence renders.
**Requirements**: TBD
**Depends on:** Phase 35
**Plans:** 1 plan

Plans:
- [ ] `36-01-PLAN.md` — Memory-context collapse, owner arbitration, and low-noise working-memory assembly

Recommended next step:
- plan and execute this after `35`, because the remaining product pain is now packet assembly quality:
  - too many overlapping sections
  - duplicated factual renders across shelves
  - layered authority notes
  - owner selection happening too late

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is not another behavior-compliance phase and not a broad retrieval rewrite
- it exists because the current system still assembles working memory as concatenated sections rather than one owner-arbitrated packet
- accepted outcomes:
  - the hot-path memory packet is materially quieter and more coherent
  - owner arbitration happens before broad section concatenation
  - duplicated truths do not appear multiple times just because they are reachable from:
    - profile
    - graph
    - continuity
    - transcript
  - the runtime no longer adds two different high-authority wrapper layers around the same memory payload
  - continuity rendering collapses toward one bounded representation instead of multiple partially overlapping ones
  - operating truth can outrank continuity-derived prose when it exists
  - contract material appears in the hot path only when its smaller ordinary-turn lane is genuinely justified
  - token spend shifts from section duplication toward higher-signal evidence
- rejected outcomes:
  - solving the noise problem with more cue farms, marker lists, or special cases
  - hiding the same duplicated evidence behind prettier wording
  - keeping multiple overlapping sections “for safety” when they have no distinct owner value
  - removing exact recall or durable truth in order to make the packet look shorter
  - treating transcript stuffing as the fallback answer to owner-arbitration gaps

### Phase 37. Canonical style-contract capture sanitization, polluted-contract quarantine, and reset-proof promotion (INSERTED)

**Goal:** Fix the proven live failure where Brainstack can promote polluted conversational text into the canonical style contract, causing reset-proof misrecall and degraded hot-path policy projection even after the user explicitly finalized a newer rule set.
**Requirements**: TBD
**Depends on:** Phase 36
**Plans:** 1 plan

Plans:
- [ ] `37-01-PLAN.md` — Canonical style-contract capture sanitization, polluted-contract quarantine, and reset-proof promotion

Recommended next step:
- plan and execute this after `36`, because the current blocker is no longer packet noise alone:
  - canonical style-contract capture can swallow user-speech framing
  - patch promotion can preserve stale headings and wrong rule-count titles
  - compiled hot-path policy can be rebuilt from already-polluted canonical truth
  - session reset then faithfully re-exposes corrupted authority instead of the user’s final intent

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is not a broad behavior-policy rewrite and not a new heuristic parser farm
- it exists because the current capture and promotion path can turn conversational scaffolding into canonical contract truth
- accepted outcomes:
  - explicit full-contract replace / supersede becomes a first-class operation instead of being forced through full-parse-or-small-patch seams
  - canonical style-contract commits come only from bounded, structurally valid teaching payloads
  - patch mode can update existing canonical rules without inheriting surrounding chat framing
  - punctuation semantics remain faithful to the user’s true rule intent:
    - “forbid em dash” stays distinct from
    - “forbid all dash-like punctuation”
  - polluted candidate titles, headings, and rule lines are rejected before canonical promotion
  - compiled policy promotion refuses to rebuild the hot path from obviously polluted canonical contract state
  - already-polluted principals can be repaired or quarantined safely instead of silently remaining authoritative
  - reset behavior becomes trustworthy because the persisted canonical contract is clean
  - the fix stays donor-friendly, exact-recall-safe, and token-disciplined
- rejected outcomes:
  - solving this by adding more cue farms or user-specific allow/deny phrases
  - weakening multi-message rule teaching so far that explicit user-authored contract capture stops working
  - silently deleting canonical truth without an auditable repair path
  - masking polluted canonical state with more prompt-time patching
  - broad benchmark-shaped behavior tuning instead of fixing the canonical capture seam

### Phase 38. Append-safe operating truth persistence and bounded natural capture widening (INSERTED)

**Goal:** Remove the current operating-truth overwrite risk and make operating/task truth promotion more natural for real chat, without turning Brainstack into a heuristic planner or ontology farm.
**Requirements**: TBD
**Depends on:** Phase 35
**Plans:** 1 plan

Plans:
- [ ] `38-01-PLAN.md` — Append-safe operating truth persistence and bounded natural capture widening

Recommended next step:
- execute this after `37`, because a real second-brain cannot silently collapse multiple commitments or next steps into one record and still claim reliable operating memory

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is not a broad operating-kernel rewrite
- it exists because the current operating substrate still has:
  - append-vs-singleton correctness risk
  - overly heading-shaped capture requirements for natural chat
- accepted outcomes:
  - `current_commitment` and `next_step` no longer overwrite each other through singleton stable keys
  - operating truth can safely preserve multiple simultaneous commitments and next steps
  - bounded natural-chat capture improves without turning into a cue farm
  - task / operating promotion gains a narrower middle ground between:
    - ignored continuity-only text
    - and immediate canonical commit
  - the result stays donor-first, auditable, and free of ontology sprawl
- rejected outcomes:
  - broad autonomous planner behavior
  - giant schema expansion
  - user-specific or language-specific heuristic farms
  - silently deduplicating away distinct commitments or next steps

### Phase 38.1. Owner-first control-plane routing and cue-list de-escalation (INSERTED)

**Goal:** Demote cue-list routing inside the control plane so owner-derived signals and route results become the primary packet-shaping inputs, with heuristics reduced to narrow fallback only.
**Requirements**: TBD
**Depends on:** Phase 38
**Plans:** 1 plan

Plans:
- [ ] `38.1-01-PLAN.md` — Owner-first control-plane routing and cue-list de-escalation

Recommended next step:
- execute this before `39`, because graph-side work should not be used to compensate for a cue-first packet shell

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is not a broad retrieval rewrite and not a new planner layer
- it exists because the current `control_plane` still relies too centrally on cue lists for packet shaping
- accepted outcomes:
  - owner-derived signals become primary in `control_plane`
  - route-resolver outputs and retrieved support drive packet shaping more than raw cue hits
  - cue lists remain only as narrow boundary fallback where no stronger signal exists
  - the result stays donor-first, auditable, and token-disciplined
- rejected outcomes:
  - replacing one cue farm with a bigger cue farm
  - hiding routing behavior behind opaque local heuristics
  - breaking owner-backed retrieval or route-resolver seams
  - broad parser rewrites inside the control plane

### Phase 39. Typed graph ingress contract hardening and observability (INSERTED)

**Goal:** Strengthen the typed graph-evidence boundary so graph truth handling is provenance-clean, fail-closed, auditable, and ready for future multimodal producers without turning text extraction into the graph layer’s main intelligence.
**Requirements**: TBD
**Depends on:** Phase 38.1
**Plans:** 1 plan

Plans:
- [ ] `39-01-PLAN.md` — Typed graph ingress contract hardening and observability

Recommended next step:
- execute this after `38.1`, because the next graph-side win is boundary correctness and observability, not broader local phrase extraction

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is not a giant knowledge-graph rebuild and not a graph regex-expansion phase
- it exists because the typed graph boundary still needs stronger receipts, traceability, and contract clarity before any donor-backed semantic widening is safe
- accepted outcomes:
  - typed graph truth remains fail-closed and provenance-clean
  - graph ingress receipts and observability become clearer and more inspector-friendly
  - malformed or unsupported graph evidence proves explicit fail-closed behavior
  - source, `hermes-final`, and live runtime all prove the tightened graph contract consistently
  - the graph lane becomes safer for future multimodal producers without text-only coupling
- rejected outcomes:
  - broad language-specific regex farms
  - phrase-table multilingual harvest
  - text-only graph intelligence layers disguised as “bounded widening”
  - packet-noise regressions from graph ambition creep

### Phase 40. Canonical memory integrity, historical repair, read-path convergence, and deterministic debug surfaces (INSERTED)

**Goal:** Close the now-proven integrity gap by establishing one convergent memory authority across durable writes, ordinary reads, historical repair, and operator proof surfaces.
**Requirements**: TBD
**Depends on:** Phase 39
**Plans:** 1 plan

Plans:
- [ ] `40-01-PLAN.md` — Canonical memory integrity, historical repair, read-path convergence, and deterministic debug surfaces

Recommended next step:
- execute this after `39`, because the next proven blocker is now memory authority divergence across write, read, repair, and debug surfaces rather than packet noise or graph ingress alone

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is not a style-only patch and not a new prompt-governance layer
- it exists because the current runtime still allows:
  - nominal read surfaces to trigger durable memory mutation
  - polluted historical canonical state to remain active
  - stale style/profile residue to help re-grow contract-shaped fallback authority
  - compiled policy and ordinary-turn active lane to drift away from exact canonical lineage
  - debugging to mix model narration with real runtime truth
- accepted outcomes:
  - nominal read surfaces do not mutate durable truth classes
  - polluted historical generations can be quarantined, superseded, or tombstoned audibly
  - transcript/profile style residue can no longer regenerate active communication authority when canonical style truth exists
  - compiled policy, exact canonical recall, and the smaller active lane converge on one authority lineage
  - operator debug truth is out-of-band, machine-readable, and explicitly separated from host/runtime layers
  - fresh stores and dirty stores both prove correct behavior
  - the result stays donor-first, fail-closed, multimodal-safe, and free of new heuristic farms
- rejected outcomes:
  - using memory wipes as the permanent fix
  - fixing only style writes while leaving task or operating read-side mutation alive
  - letting profile or graph rows keep acting as shadow contract authority
  - hiding the issue behind prompt wording or query-shape logic

### Phase 40.1. Owner-first routing completion and route-resolution fail-closed convergence (INSERTED)

**Goal:** Finish the remaining routing residuals so owner-derived signals and route evidence dominate packet shaping, with route-resolution failure handled explicitly instead of silently redefining truth mode.
**Requirements**: TBD
**Depends on:** Phase 40
**Plans:** 1 plan

Plans:
- [ ] `40.1-01-PLAN.md` — Owner-first routing completion and route-resolution fail-closed convergence

Recommended next step:
- execute this after `40`, because routing residuals should remain a separate sister gate rather than being smuggled into the authority-integrity phase

Recommended agent effort:
- `xhigh`

Planning note:
- this phase exists because routing still retains query-shape residual influence after `38.1`
- accepted outcomes:
  - owner-derived signals clearly outrank broad cue lists
  - route-resolution failure becomes explicit and inspectable
  - residual cue logic remains bounded fallback only
- rejected outcomes:
  - new cue farms
  - silent route-failure behavior drift
  - routing opacity

### Phase 40.2. Durable preference ingress hardening and style-authority anti-regeneration follow-through (INSERTED)

**Goal:** Harden transcript/profile-derived durable preference ingress so it cannot recreate long-lived style residue or contract-shaped shadow truth after Phase 40 repair.
**Requirements**: TBD
**Depends on:** Phase 40
**Plans:** 1 plan

Plans:
- [ ] `40.2-01-PLAN.md` — Durable preference ingress hardening and style-authority anti-regeneration follow-through

Recommended next step:
- execute this after `40`, because anti-regeneration in the authority lane should land first, then the broader durable-ingress cleanup can be narrowed safely

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is not permission to widen transcript heuristics
- accepted outcomes:
  - durable preference ingress becomes narrower and more contract-safe
  - profile truth remains useful without impersonating canonical contract authority
  - repaired style truth does not get re-contaminated by transcript/profile write seams
- rejected outcomes:
  - broad phrase tables as main intelligence
  - transcript-derived shadow contract rebuilds
  - throwing away legitimate long-lived profile truth

### Phase 40.3. Graph value frontier, producer-aligned semantic expansion, and proof (INSERTED)

**Goal:** Improve graph usefulness after integrity work through producer-aligned typed evidence evolution rather than a graph-side heuristic text engine.
**Requirements**: TBD
**Depends on:** Phase 40
**Plans:** 1 plan

Plans:
- [ ] `40.3-01-PLAN.md` — Graph value frontier, producer-aligned semantic expansion, and proof

Recommended next step:
- execute this after `40`, once authority integrity is stable, because graph value should grow from typed producer improvement rather than compensating for unresolved memory-integrity drift

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is the future graph value frontier, not a return to graph-side regex widening
- accepted outcomes:
  - typed ingress remains fail-closed
  - graph value widens through producer-aligned evidence
  - multimodal extension remains open
- rejected outcomes:
  - hidden text-only graph intelligence
  - phrase-family graph engines
  - provenance loss
  - solving debug by asking the model to explain what it thinks it received
  - folding unrelated routing or graph intelligence expansion into this integrity phase

### Phase 41. Ultra-deep full-system debt, defect, residual heuristic, fallback, and principle-compliance audit for strict inspector readiness (INSERTED)

**Goal:** Produce the most complete possible inspector-facing inventory of defects, technical debt, residual heuristics, fallback seams, proof gaps, deploy drifts, and principle violations across the full Brainstack and deployed Hermes/Bestie stack before the next corrective milestone.
**Requirements**: TBD
**Depends on:** Phase 40.3
**Plans:** 1 plan

Plans:
- [ ] `41-01-PLAN.md` — Ultra-deep full-system debt, defect, residual heuristic, fallback, and principle-compliance audit for strict inspector readiness

Recommended next step:
- execute this immediately after `40.3`, because the next need is not another local fix but a complete, unsparing debt map before the strict external review

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is an audit and debt-enumeration phase, not a prompt-polishing phase and not a stealth implementation phase
- accepted outcomes:
  - file-level inventory of open defects and technical debt
  - explicit principle-compliance review against `/IMMUTABLE-PRINCIPLES.md`
  - clear split between:
    - already fixed
    - still open
    - residual but bounded
    - deploy-only drift
  - runtime, source, planning, test, proof, and deploy surfaces all covered
  - findings preserved incrementally in durable audit artifacts
- rejected outcomes:
  - “looks good enough” summary without file-level proof
  - hiding residual heuristics because they are old
- collapsing deploy drift, source debt, and product limitations into one vague bucket
- claiming full product readiness without explicit proof

### Phase 42. Owner-first memory routing completion, route-semantics de-heuristicization, and authority convergence (INSERTED)

**Goal:** Remove the remaining query-shape and cue-table authority from Brainstack routing so exact recall, ordinary-turn memory guidance, and route selection converge on owner-derived signals and explicit authority lineage rather than fallback synthesis.
**Requirements**: TBD
**Depends on:** Phase 41
**Plans:** 1 plan

Plans:
- [ ] `42-01-PLAN.md` — Owner-first memory routing completion, route-semantics de-heuristicization, and authority convergence

Recommended next step:
- execute this first after `41`, because the current residual cue-routing and multi-authority retrieval seam still distort what truth surface the user sees

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is where the remaining `control_plane` / `executive_retrieval` / `retrieval` residuals get closed
- accepted outcomes:
  - no query-shape authority on the primary Brainstack routing path
  - route semantics grounded in owner signals and explicit lineage
  - ordinary-turn lane and exact recall tied to the same authority generation
  - no pseudo-authority rebuild from fallback shelves when canonical authority exists
- rejected outcomes:
  - adding smarter cue tables instead of removing cue authority
  - hiding route fallback behind nicer wording

### Phase 42.1. Final-output typed invariant enforcement and fail-closed obedience (INSERTED)

**Goal:** Close the residual gap where Brainstack can know a typed final-output invariant, detect a violation, and still let the violating answer ship. Finish the final-output enforcement layer so typed invariants are either deterministically repaired or explicitly fail-closed rather than remaining advisory.
**Requirements**: TBD
**Depends on:** Phase 42
**Plans:** 1 plan

Plans:
- [ ] `42.1-01-PLAN.md` — Final-output typed invariant enforcement and fail-closed obedience

Recommended next step:
- execute this immediately after `42`, because the current final-output validator can still detect `remaining_violations` without forcing obedience, which leaves real user-facing rule breaks in place

Recommended agent effort:
- `xhigh`

Planning note:
- this phase is not a dash-specific patch
- accepted outcomes:
  - final-output typed invariants become real enforcement, not trace-only advisory state
  - the runtime may not silently ship responses with detected typed invariant violations
  - repair vs fail-closed behavior becomes explicit, deterministic, and proofable
  - obedience proof covers the whole typed invariant bug class, not one wording example
- rejected outcomes:
  - special-casing dash punctuation as a one-off hack
  - benchmark-shaped output-policing that does not improve kernel correctness
  - silent auto-rewrites with no operator-visible proof surface

### Phase 43. Gateway runtime fail-closed delivery, compatibility-seam reduction, and operational drift closure (INSERTED)

**Goal:** Reduce or eliminate the remaining best-effort and deprecated fallback seams in gateway delivery and startup so the live runtime is more explicit, less compatibility-heavy, and easier to inspect under failure.
**Requirements**: TBD
**Depends on:** Phase 42
**Plans:** 1 plan

Plans:
- [ ] `43-01-PLAN.md` — Gateway runtime fail-closed delivery, compatibility-seam reduction, and operational drift closure

Recommended next step:
- execute this after `42`, because runtime fallback and boot compatibility seams still weaken inspector-grade operational clarity

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - gateway delivery fallback seams minimized and explicitly bounded
  - deprecated boot/runtime env fallbacks reduced or retired
  - provider/runtime failure surfaces classified cleanly instead of drifting between config, economics, and source logic
  - deploy/runtime drift warnings either resolved or explicitly quarantined
- rejected outcomes:
  - papering over fallback behavior with logging only
  - keeping silent degrade-open paths because they are operationally convenient

### Phase 44. Legacy storage, config, and compatibility retirement across session and memory surfaces (INSERTED)

**Goal:** Finish the remaining migration work so session, provider, and memory subsystems stop carrying dual-storage, dual-config, or legacy alias debt that widens the ambiguity surface and maintenance burden.
**Requirements**: TBD
**Depends on:** Phase 43
**Plans:** 1 plan

Plans:
- [ ] `44-01-PLAN.md` — Legacy storage, config, and compatibility retirement across session and memory surfaces

Recommended next step:
- execute this after `43`, because the system still carries JSONL, legacy provider/config, and legacy graph compatibility seams that complicate both runtime truth and maintenance

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - legacy session transcript fallback retired or isolated behind explicit migration gates
  - legacy provider/config alias surfaces reduced
  - compatibility debt around legacy graph extraction and memory paths narrowed further
  - migration status becomes inspectable rather than implicit
- rejected outcomes:
  - indefinite coexistence of old and new storage/config paths
  - “temporary” compatibility shims with no retirement plan

### Phase 45. Orchestration hub decomposition, bridge-node blast-radius reduction, and modularity recovery (INSERTED)

**Goal:** Break down the largest orchestration hubs and high-betweenness chokepoints so the product stops depending on a handful of giant functions and bridge classes with outsized blast radius.
**Requirements**: TBD
**Depends on:** Phase 44
**Plans:** 1 plan

Plans:
- [ ] `45-01-PLAN.md` — Orchestration hub decomposition, bridge-node blast-radius reduction, and modularity recovery

Recommended next step:
- execute this after the authority and compatibility seams are clean, because decomposition before truth/runtime convergence would just reshuffle unstable logic

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - smaller orchestration functions in the worst hotspot files
  - lower bridge-node blast radius in gateway/runtime chokepoints
  - cleaner community boundaries and reduced cross-community coupling where practical
- rejected outcomes:
  - cosmetic splitting that keeps the same hidden global coupling
  - refactors that make upstream sync harder without buying real blast-radius reduction

### Phase 46. Inspector-proof replay, hotspot coverage, and deterministic evidence harness (INSERTED)

**Goal:** Build the proof layer needed for strict external inspection: direct high-fidelity replay, hotspot-targeted regression coverage, and deterministic evidence artifacts for the biggest integrity and runtime seams.
**Requirements**: TBD
**Depends on:** Phase 45
**Plans:** 1 plan

Plans:
- [ ] `46-01-PLAN.md` — Inspector-proof replay, hotspot coverage, and deterministic evidence harness

Recommended next step:
- execute this after structural cleanup, because proof should lock the corrected system rather than bless a moving target

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - replay harnesses for dirty-store, clean-store, fallback, and route-convergence scenarios
  - direct proof on the biggest orchestration hubs and bridge nodes
  - inspector-readable evidence artifacts that separate source truth, runtime truth, and deploy truth
- rejected outcomes:
  - test-count inflation without targeting the real hotspots
  - benchmark cosmetics instead of failure-mode proof

### Phase 47. Producer-aligned typed graph and multimodal memory value frontier expansion (INSERTED)

**Goal:** Re-grow product value after the anti-heuristic cleanup by expanding graph and multimodal memory usefulness only through producer-aligned typed evidence, not by reintroducing regex or cue-farm extraction.
**Requirements**: TBD
**Depends on:** Phase 46
**Plans:** 1 plan

Plans:
- [ ] `47-01-PLAN.md` — Producer-aligned typed graph and multimodal memory value frontier expansion

Recommended next step:
- execute this last in the corrective chain, after integrity, runtime, compatibility, structure, and proof are all in place

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - richer typed graph and multimodal producer inputs
  - higher value memory surfaces without reopening heuristic drift
  - product value uplift after the cleanup phases, not before
- rejected outcomes:
  - raw-text graph widening
  - fallback to heuristic extraction because it is faster

### Phase 48. Live chat authority bootstrap, enforcement, recall, and gateway stabilization (INSERTED)

**Goal:** After the live memory wipe, make ordinary Bestie chat dependable by converging authority bootstrap, compiled enforcement, natural rule recall, transcript continuity, user-surface hygiene, and reminder scheduling into one live-stable runtime path.
**Requirements**: TBD
**Depends on:** Phase 47
**Plans:** 1 plan

Plans:
- [ ] `48-01-PLAN.md` — Live chat authority bootstrap, enforcement, recall, and gateway stabilization

Recommended next step:
- execute this next if the live memory store is being reset, because a clean wipe without bootstrap, enforcement, recall, persistence, and UX containment would just recreate the same broken chat behavior

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - wiped live memory can bootstrap one clean style authority and one compiled policy without manual DB surgery
  - final output cannot silently ship when active typed invariants are known but unenforced
  - natural-language rule questions route to style authority instead of drifting into transcript recall
  - transcript persistence, tool-trace containment, and reminder timezone correctness are live-stable
  - the resulting runtime behaves like one coherent product surface rather than a working kernel plus broken host shell
- rejected outcomes:
  - benchmark-chasing for one chat log instead of general live chat stabilization
  - new heuristic farms, regex nets, or prompt band-aids that hide the same authority/runtime split

### Phase 49. Live replay stabilization loop, user-facing chat correction, and no-feature recovery gate (INSERTED)

**Goal:** Freeze feature growth and recover dependable live chat quality by running a closed-loop replay-and-correction phase against real failing conversations until the user-facing runtime stops leaking blockers, tool traces, routing drift, and scheduling mistakes.
**Requirements**: TBD
**Depends on:** Phase 48
**Plans:** 1 plan

Plans:
- [ ] `49-01-PLAN.md` — Live replay stabilization loop, user-facing chat correction, and no-feature recovery gate

Recommended next step:
- execute this immediately after `48`, because the remaining failures are now product-surface regressions and sequencing debt, not missing capability layers

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - a bounded replay pack built from real failing chats becomes the main acceptance surface for this corrective loop
  - blocked-output enforcement never leaks internal Brainstack blocker text to the user
  - internal tool progress never leaks into ordinary chat
  - natural rule-recall questions resolve to style authority on the live path
  - transcript persistence and reminder timezone correctness are proven on the same end-to-end runtime path
  - no additional feature work is allowed to bypass the replay gate
- rejected outcomes:
  - adding new memory features before the live chat path is stable
- synthetic benchmark chasing or one-off prompt band-aids
- declaring success from local unit green while the docker/live replay pack still fails

### Phase 50. Donor-first de-escalation recovery, thin-shell rebuild, and fresh-upstream live proving (INSERTED)

**Goal:** Step back from the over-constrained host-level rule system and rebuild a working product on fresh upstream Hermes where the shell only orchestrates donor memory layers instead of acting like a second behavior engine.
**Requirements**: TBD
**Depends on:** Phase 48
**Plans:** 1 plan

Plans:
- [ ] `50-01-PLAN.md` — Donor-first de-escalation recovery, thin-shell rebuild, and fresh-upstream live proving

Recommended next step:
- execute this in place of any further `49` expansion, because the main problem is now overbuilt host control rather than missing corrective patches

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - the execution baseline moves to the fresh upstream Hermes checkout at `/home/lauratom/Asztal/ai/finafina`
  - the product returns to a thin orchestration shell around donor memory layers
  - host-level hard behavior gating, generic blocker fallbacks, and rule-engine creep are removed or sharply reduced
  - proving uses a fresh runtime/profile baseline rather than historically drifted Bestie state
  - the phase ends with a rolling live-test-and-rethink loop on the simplified product
- rejected outcomes:
- continuing to patch the old drifted host path as if more local fixes will restore product quality
- adding new capabilities, shelves, or orchestration layers during the recovery
- reintroducing broad host-level rule governance in the name of compliance or polish

### Phase 51. Brainstack-Hermes synergy audit, graph proof, and donor-fit gap map (INSERTED)

**Goal:** Prove whether the rebuilt Brainstack plugin is genuinely synergistic with Hermes as a donor-first memory provider, or whether the integration is still only superficially thin on paper while remaining opaque, oversized, or weakly inspectable in practice.
**Requirements**: TBD
**Depends on:** Phase 50
**Plans:** 1 plan

Plans:
- [ ] `51-01-PLAN.md` — Brainstack-Hermes synergy audit, graph proof, and donor-fit gap map

Recommended next step:
- execute this immediately after `50`, because the rebuilt thin-shell direction now needs an explicit truth-first verdict about whether Brainstack actually helps Hermes or merely attaches to it

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - the audit proves which parts of the integration are truly donor-first and synergistic
  - the audit identifies which parts remain merely paper-thin or weakly inspectable
  - graph evidence, blast-radius evidence, and runtime seam evidence are all brought into one verdict
  - the output is a concrete donor-fit gap map, not a vague opinion
- rejected outcomes:
  - declaring “synergy” from local green tests alone
  - ignoring graph invisibility or inspectability debt because runtime behavior seems acceptable
  - jumping back into feature work before the integration fit is honestly judged

### Phase 52. Native user-profile re-anchoring, Brainstack kernel-only recovery, and file-level keep/demote/remove/rebuild map (INSERTED)

**Goal:** Re-anchor explicit user/profile authority to Hermes' native `USER.md` / `MEMORY.md` path, demote Brainstack custom profile governance back to a true memory-kernel role, and define a file-level keep/demote/remove/rebuild plan so the product becomes a working chat-first host with a donor-first memory shell.
**Requirements**: TBD
**Depends on:** Phase 50, Phase 51
**Plans:** 1 plan

Plans:
- [ ] `52-01-PLAN.md` — Native user-profile re-anchoring, Brainstack kernel-only recovery, and file-level keep/demote/remove/rebuild map

Recommended next step:
- execute this before any further Brainstack capability work, because the current product still lacks a stable authority hierarchy between native Hermes profile memory and Brainstack-managed memory lanes

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - Hermes native `USER.md` / `MEMORY.md` becomes the first-class explicit profile path again
  - Brainstack mirrors and augments native memory writes instead of replacing built-in user-profile authority
  - Brainstack keeps continuity, transcript, operating/task truth, graph, and corpus roles
  - ordinary chat remains chat-first while memory augmentation stays donor-first
  - the output is a concrete file-level keep/demote/remove/re-anchor map, not a vague architectural preference
- rejected outcomes:
  - gutting Brainstack donor intelligence in the name of simplification
  - keeping Brainstack custom profile/style governance as a parallel first-class user-profile system
  - introducing new capability work before native-profile primacy and kernel scope are cleanly re-established

### Phase 53. Live multi-session Discord UAT, reset proof, and product-readiness correction loop (INSERTED)

**Goal:** Prove and harden the rebuilt Hermes-native-profile + Brainstack-kernel stack in real Discord operation through a rolling multi-session live test matrix, with explicit reset, contradiction, reminder, and ordinary-chat quality gates, until the product is genuinely deploy-ready rather than locally green.
**Requirements**: TBD
**Depends on:** Phase 52
**Plans:** 1 plan

Plans:
- [ ] `53-01-PLAN.md` — Live multi-session Discord UAT, reset proof, and product-readiness correction loop

Recommended next step:
- execute this immediately after phase 52, because architecture is now in the right place but real product readiness still needs live, repeated, multi-step proof

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - the system is proven in real Discord conversation, not only local replay and unit tests
  - explicit profile capture, mirrored Brainstack recall, ordinary chat naturalness, reset behavior, contradiction handling, and reminder behavior are all exercised in one coherent UAT ladder
  - the phase includes repeated live correction loops, not a one-shot test pass
  - the end state is a product-readiness verdict with concrete pass/fail evidence
- rejected outcomes:
  - stopping at smoke tests or isolated local harnesses
  - hiding regressions behind fallback copy or selective scenario choice
  - introducing new capabilities instead of correcting observed live failures
  - declaring “ready” before the full multi-session matrix is green

### Phase 54. Native explicit truth atomicity, Discord surface precedence, and explicit pack persistence recovery (INSERTED)

**Goal:** Fix the remaining deep Discord-surface defect family by making native explicit truth writes atomic and first-class, separating transport identity from addressing authority, and persisting explicit multi-rule packs as durable truth without reintroducing Brainstack governance or heuristic schema drift.
**Requirements**: TBD
**Depends on:** Phase 53
**Plans:** 1 plan

Plans:
- [ ] `54-01-PLAN.md` — Native explicit truth atomicity, Discord surface precedence, and explicit pack persistence recovery

Recommended next step:
- execute this immediately after Phase 53, because the remaining failure is no longer broad UAT uncertainty but one concrete host/native-truth boundary defect family on the real Discord surface

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - explicit user/addressing truth is stronger than Discord handle metadata on the user-facing surface
  - explicit multi-rule teaching is persisted as first-class durable truth rather than best-effort free-chat mining
  - Brainstack remains a mirror/kernel and does not regain profile- or behavior-governor authority
  - the fix is generic and multimodal-safe, not a narrow personal-field schema
- rejected outcomes:
  - adding new behavior policies, guardrails, or ordinary-turn communication-governor logic
  - adding field enums, locale-specific parsers, or regex farms to force the Discord path green

### Phase 55. Discord explicit rule-pack fidelity, ordinary-turn compliance, and final live proof (INSERTED)

**Goal:** Close the remaining product gap by making explicitly taught rule packs persist and recall with full fidelity, drive ordinary Discord behavior without warnings or leaks, and prove the result on the real running Discord surface without benchmaxing or heuristic shortcuts.
**Requirements**: TBD
**Depends on:** Phase 54
**Plans:** 1 plan

Plans:
- [x] `55-01-PLAN.md` — Discord explicit rule-pack fidelity, ordinary-turn compliance, and final live proof
- [x] `55-EXECUTION-RESULT.md` — Execution proof and closeout

Recommended next step:
- execute this immediately after Phase 54, because the remaining failure is no longer broad architecture uncertainty but one narrow product defect family: explicit rule-pack truth exists too weakly in the real Discord product path to guarantee compliant ordinary behavior and high-fidelity recall

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - explicitly taught multi-rule packs persist as first-class durable truth, not as best-effort free-chat residue
  - same-session and post-reset recall return the full taught rule pack with no omissions or semantic inversions
  - ordinary Discord replies follow the stored explicit rule pack without first warning, re-asking, or leaking internal lifecycle/status text
  - final readiness is proven on the running Discord product with two consecutive fresh-state green runs
- rejected outcomes:
  - adding any new behavior-governor, policy layer, or prompt-only control path to force compliance
  - encoding the current Hungarian 21/22-rule pack as a built-in taxonomy, regex farm, locale parser, or special-case extractor
  - claiming readiness from harness-only proof, selective cases, or benchmark-shaped artifacts
  - accepting a result where recall works but ordinary Discord behavior still drifts, leaks, or asks the user to restate the rules
  - relying on the model to “probably remember to write everything” when explicit durable truth is being taught
  - patching the symptom at reply time instead of fixing the host/native explicit truth contract

### Phase 56. Live-state canonicalization, behavior-authority demotion, transcript hygiene, and source-of-truth install proof (INSERTED)

**Goal:** Remove the remaining inspector-blocking defects by canonicalizing deployed explicit truth state, stopping explicit native rule packs from becoming active Brainstack behavior authority, preventing internal status text from contaminating transcript memory, and proving the result from the `Brainstack-phase50` source-of-truth repo via wizard install onto a fresh Hermes checkout.
**Requirements**: TBD
**Depends on:** Phase 55
**Plans:** 1 plan

Plans:
- [ ] `56-01-PLAN.md` — Live-state canonicalization, behavior-authority demotion, transcript hygiene, and source-of-truth install proof

Recommended next step:
- execute this immediately after Phase 55 because the remaining failures are no longer broad product-readiness questions but concrete inspector-blocking defects in deployed state migration, behavior-authority residue, and transcript contamination

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - `Brainstack-phase50` is the only code source of truth for the fix
  - `finafina` is treated as an installed runtime target, not a second implementation surface
  - a fresh Hermes checkout can be brought to the corrected state by the wizard/install path from the source-of-truth repo
  - deployed `USER.md` / native explicit profile state is canonicalized into the Phase 54/55 explicit-truth contract
  - the remaining defect family is treated as both deployed-state dirtiness and active authority residue, not just cosmetic runtime mess
  - explicit rule packs remain native explicit truth plus bounded mirror/archive and do not produce active `behavior_contracts` or `compiled_behavior_policies`
  - internal interrupt/status strings are excluded from transcript memory and therefore cannot leak back through recall
  - proof is split cleanly into installed runtime / provider-path proof and real Discord UI proof on the same installed runtime
  - after this phase, the default next mode is stabilization and debt paydown, not new capability work
- rejected outcomes:
  - hand-fixing `finafina` in ways the wizard cannot reproduce
  - keeping a fresh-state-only green proof while deployed long-lived state remains degraded
  - allowing Brainstack to keep a behavior-authority lane for explicit native rule packs
  - solving transcript contamination with output hiding while polluted transcript rows continue to persist
  - any user-specific or locale-specific patch that only rescues the current Discord example
  - treating post-56 residual debt as acceptable justification for immediately starting new feature phases

### Phase 57. Live Discord stuck-run recovery, fail-closed runtime containment, native scheduler truth, and reset leak cleanup (INSERTED)

**Goal:** Eliminate the remaining live-runtime product defects by stopping ordinary Discord turns from hanging until manual reset, making Brainstack graph/provider failure paths fail closed instead of half-open, restoring truthful native scheduler behavior, removing user-facing reset leakage, and proving the fix from the `Brainstack-phase50` source-of-truth install path.
**Requirements**: TBD
**Depends on:** Phase 56
**Plans:** 1 plan

Plans:
- [ ] `57-01-PLAN.md` — Live Discord stuck-run recovery, fail-closed runtime containment, native scheduler truth, and reset leak cleanup
- execution artifacts:
  - `57-EXECUTION-RESULT.md`
  - `57-LIVE-RUNTIME-STUCK-RUN-PROOF.md`
  - `57-SCHEDULER-TRUTH-PROOF.md`
  - `57-DISCORD-UI-PROOF-NOTE.md`

Recommended next step:
- complete

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - `Brainstack-phase50` remains the only edited source repo for the fix
  - the installed Discord runtime no longer leaves ordinary user turns hanging until `/reset`
  - unhealthy graph/provider paths degrade cleanly instead of leaving repeated `KuzuGraphBackend is not open` and partial-init residue in the active request path
  - provider initialization failure does not leave a misleading half-alive memory lane behind
  - reminder / cronjob acknowledgements are truthful:
    - success means a real native scheduled job exists and real Discord delivery can be observed
    - failed delivery remains observable instead of disappearing as fake one-shot success
    - failure means the user is told explicitly instead of receiving a fake success line
  - bare `Session reset.` and comparable lifecycle text no longer leak into ordinary Discord chat
  - the corrected behavior is reproduced in `finafina` by install/copy from `Brainstack-phase50`, not by hand patching the target
- rejected outcomes:
  - adding timeout cosmetics while leaving the real stuck-run root cause untouched
  - blaming Brainstack by assumption before separating host/runtime and provider fault boundaries
  - solving the scheduler bug by merely remembering a reminder fact in memory instead of creating a real native scheduled job
  - hiding reset leakage with output filtering while the wrong lifecycle text still travels through the runtime path
  - any user-specific, Hungarian-specific, or prompt-only patch that rescues only the current Discord example
  - resuming new capability work before these live-runtime correctness defects are closed

### Phase 58. Inspector-readiness debt paydown, source-of-truth release closure, persistent-state scrub, and half-wired surface reduction (INSERTED)

**Goal:** Close the remaining inspector-blocking debt by turning the `Brainstack-phase50` repo into a clean releasable source of truth, scrubbing residual live-state contamination left by older runtime paths, reducing shipped half-wired and legacy compatibility surfaces, and reconciling planning/runtime proof so the project story is coherent end to end.
**Status:** Complete
**Requirements**: TBD
**Depends on:** Phase 57
**Plans:** 1 plan

Plans:
- [x] `58-01-PLAN.md` — Inspector-readiness debt paydown, source-of-truth release closure, persistent-state scrub, and half-wired surface reduction

Recommended next step:
- stay in stabilization / debt-paydown mode; do not reopen capability work until inspector-readiness evidence actually demands it

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50` is left in a clean releasable state:
    - no unexplained dirty worktree
    - no uncommitted wizard/runtime fixes
    - no ambiguous source-of-truth drift versus the installed target
  - persistent live-state residue is scrubbed or migrated:
    - stale interrupt/status transcript rows do not remain in the live store
    - old superseded behavior-contract storage from native explicit rule packs is removed or demoted into clearly non-authoritative archival state
  - half-wired shipped surfaces are reduced:
    - dead compatibility shims, no-op governor remnants, and stale behavior-policy residue are either deleted, explicitly demoted, or justified as bounded compatibility surfaces
  - the installer and doctor prove the corrected state on an installed runtime without manual target-only edits
  - planning debt is reconciled:
    - older Phase 41 critical/high wording is either closed, remapped, or explicitly marked historical
    - manual-gate wording around Discord proof matches the actual proof standard the project is claiming
  - the phase ends with a coherent inspector-ready story:
    - source repo
    - installed runtime
    - persistent state
    - proof artifacts
    - release boundary
- rejected outcomes:
  - treating the new `croniter` wizard fix as the only remaining debt
  - blindly deleting large modules based only on automated dead-code counts without runtime-entry validation
  - keeping dirty source-of-truth fixes uncommitted while claiming inspector readiness
  - accepting residual persistent-state contamination because the fresh runtime looks clean
  - leaving legacy compatibility shims and dormant governor lanes in shipped source without an explicit keep/remove decision
  - starting new capability phases before the repo/runtime/proof debt is closed
  - solving any of this with user-specific, locale-specific, or prompt-only rescue logic

### Phase 59. Context-window attribution, cross-shelf budget allocation, and hybrid retrieval fusion hardening

**Goal:** Prove whether rapid context-window fill is actually caused by Brainstack versus the wider Hermes prompt stack, then strengthen the Brainstack side of the problem by adding a real cross-shelf budget allocator and a more coherent hybrid retrieval fusion strategy without regressing recall quality or donor boundaries.
**Status:** Complete
**Requirements**: TBD
**Depends on:** Phase 58
**Plans:** 1 plan

Plans:
- [x] `59-01-PLAN.md` — Context-window attribution, cross-shelf budget allocation, and hybrid retrieval fusion hardening

Recommended next step:
- hold here unless a new measured context-pressure complaint appears; the attribution and Brainstack-owned allocator/fusion uplift are complete

Recommended agent effort:
- `xhigh`

Planning note:
- accepted outcomes:
  - the phase begins with a hard attribution step:
    - determine how much of fast context-window fill belongs to:
      - Hermes host prompt layers
      - tool schema overhead
      - builtin memory / user-profile surfaces
      - Brainstack system-prompt projection
      - Brainstack per-turn prefetch packet
      - conversation history itself
  - the project does not assume that Brainstack is the dominant cause just because it is the memory provider
  - if Brainstack is contributing materially, the correction is kernel-quality work:
    - one stronger cross-shelf allocator
    - stronger keyword/semantic fusion
    - tighter bounded packet assembly
  - the result must improve:
    - token discipline
    - relevance
    - boundedness
    - proofability
  - source-of-truth code remains:
    - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`
  - installed proof target remains:
    - `/home/lauratom/Asztal/ai/finafina`
- rejected outcomes:
  - blaming Brainstack for context bloat without first separating host and provider contributions
  - hiding bloat by bluntly deleting evidence instead of ranking and budgeting it better
  - benchmark-only tuning that makes synthetic recall graphs prettier while hurting product retrieval
  - introducing query-specific heuristic farms or locale-specific rescue logic
- replacing MemPalace donor intent with a new vector-index ideology
- treating a candidate semantic backend swap as the same thing as fixing cross-shelf allocation
- declaring success from lower token counts alone if relevance or recall quality regresses

### Phase 60. Brainstack-universal real-world usage audit and temporal/provenance correction from a live Discord case study (INSERTED)

**Goal:** Use the current live Discord thread only as a case study to isolate and correct Brainstack-universal defects in temporal grounding, provenance trust, and durable extraction. This phase is not a generic Hermes bugfix pass.
**Status:** Executed
**Requirements**: TBD
**Depends on:** Phase 59
**Plans:** 1 plan

Plans:
- [ ] `60-01-PLAN.md` — Live Discord real-world usage audit, background-process interrupt noise, and stale-task temporal grounding correction

Recommended next step:
- follow up only on residual Brainstack-owned defects that remain after the Phase 60 provenance/temporal/task-capture hardening and live-state scrub

Recommended agent effort:
- `xhigh`

Planning note:
- accepted scope:
  - real-world Discord usage findings are now the primary trigger, not synthetic regression output
  - the live thread is evidence input and case study, not the design target
  - the phase exists to extract universal Brainstack defects from that case study, not to rescue one thread
  - the core Brainstack-owned targets are:
    - stale reminder/task text resurfacing as current truth without temporal validation
    - assistant-authored self-diagnosis and speculative implementation claims being promoted into durable Brainstack state
    - reflection-driven durable-write contamination being treated too much like ordinary user truth
    - structured `task_memory` capture accepting planning prose or reflection boilerplate as open tasks
  - current source-of-truth code remains:
    - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`
  - current installed proof target remains:
    - `/home/lauratom/Asztal/ai/veglegeshermes-source`
- rejected outcomes:
  - blaming Brainstack for background-process / execute-code churn without proving the ownership boundary
  - expanding the phase into generic Hermes cron, gateway, or Discord cleanup
  - solving stale reminder leakage with user-specific or locale-specific prompt hacks
  - broad host surgery in the wizard without proving that a narrower seam is required for Brainstack correctness
  - deleting transcript/continuity storage wholesale instead of fixing temporal grounding, provenance trust, and stale-evidence selection
  - declaring success from one cleaned-up response if the same universal evidence/trust failure can still recur for another user or another task path

### Phase 61. Brainstack restart-surviving recent-work recall, operating-summary authority, and session-search demotion (INSERTED)

**Goal:** Make Brainstack answer broad "what were we just doing / what did we just fix / did the previous phase land" recap questions after restart from Brainstack-owned durable operating truth instead of falling through to expensive transcript search.
**Status:** Completed
**Requirements**:
- remove active cue-list routing from the task / operating / recent-work path
- make restart recap rely on principal-scoped operating truth with session provenance
- keep `session_search` as secondary transcript-detail recovery only
- preserve regression coverage on the previously hardened memory / session-search / cron / stale-guard surfaces
**Depends on:** Phase 60
**Plans:** 1 plan

Plans:
- [x] `61-01-PLAN.md` — Brainstack restart-surviving recent-work recall, operating-summary authority, and session-search demotion

Recommended next step:
- execute Phase 61.1 first, because live evidence now shows the new structured-understanding seam is carrying too much ordinary-kernel authority too early

Recommended agent effort:
- `xhigh`

Execution result:
- source-of-truth recent-work recall path now uses `structured_understanding.py` instead of task/operating cue tables
- restart recap authority is carried by principal-scoped operating truth plus session provenance
- the native aggregate phrase-planner was disabled until a structured non-heuristic planner exists
- the live Tier-2 logistics regex supplement was removed from the active extraction path
- reproduced on `/home/lauratom/Asztal/ai/veglegeshermes-source`
- rebuilt live runtime returned:
  - `running; connected=discord`
  - container health `healthy`
  - restart count `0`
- regression ring result:
  - `265 passed in 6.98s`

Planning note:
- accepted scope:
  - current source-of-truth remains:
    - `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`
  - current proof target remains:
    - `/home/lauratom/Asztal/ai/veglegeshermes-source`
  - the core universal defect is now:
    - Brainstack stores relevant recent-work evidence in the live DB, but ordinary restart recap queries still produce an empty Brainstack recall packet
  - accepted Brainstack-owned targets are:
    - missing or under-populated durable operating truth for recent active work and major completed outcomes
    - recall routing that fails broad prior-work recap asks and therefore leaves usable Brainstack state unprojected
    - over-reliance on transcript/session search as a substitute for Brainstack restart-surviving recent-work memory
    - cross-session recall that is too tied to exact query wording or current-session boundaries

### Phase 61.1. Brainstack structured-understanding stabilization, availability bounds, and no-heuristic degraded mode (INSERTED)

**Goal:** Stabilize the `v1.0.17` Brainstack kernel transition in place so ordinary Brainstack behavior no longer becomes fragile when `structured_understanding` times out, errors, or returns unusable payloads, without rolling back to heuristic routing.
**Status:** Completed
**Requirements**:
- preserve the no-heuristic architecture direction from `v1.0.17`
- reduce the availability blast radius of `structured_understanding`
- define a bounded fact-safe degraded mode for ordinary Brainstack behavior
- freeze release churn until the kernel seam is stable enough for further Brainstack work
**Depends on:** Phase 61
**Plans:** 1 plan

Plans:
- [x] `61.1-01-PLAN.md` — Brainstack structured-understanding stabilization, availability bounds, and no-heuristic degraded mode

Recommended next step:
- execute Phase 62 next, because the ordinary-kernel seam is now bounded enough that live-state authority work no longer sits directly on top of repeated structured-understanding churn

Recommended agent effort:
- `xhigh`

Execution result:
- source-of-truth stabilization landed in:
  - `brainstack/structured_understanding.py`
  - `brainstack/executive_retrieval.py`
- the phase kept the no-heuristic direction and did not roll back to `v1.0.16`
- structured-understanding failures now degrade explicitly to:
  - fact route for query understanding
  - no-capture mode for capture understanding
- degraded responses are not cached as success responses
- the ordinary read path no longer performs the duplicate fallback `infer_query_understanding(...)` call inside `executive_retrieval.py`
- live target reproduction on `/home/lauratom/Asztal/ai/veglegeshermes-source`:
  - rebuilt runtime healthy
  - Discord connected
  - regression ring: `265 passed in 6.61s`

Planning note:
- accepted scope:
  - Brainstack-owned stabilization of the `structured_understanding` seam
  - narrowing mandatory structured-understanding dependence in ordinary read/write behavior
  - explicit, safe degraded mode when structured understanding is unavailable
  - release discipline strong enough to stop feature churn on top of an unstable kernel
- rejected scope:
  - rollback to `v1.0.16`
  - restoring cue tables, phrase farms, or locale-specific routing
  - provider-specific rescue logic as the architectural fix
  - generic Hermes auxiliary-client rewrite
  - folding `Phase 62` live-state truth modeling into this stabilization phase
- rejected outcomes:
  - declaring success because timeouts happen less often while the kernel still depends on live understanding success for ordinary correctness
  - a hidden heuristic fallback presented as degraded mode
  - transcript or tool fallback presented as if Brainstack memory had worked
  - shipping another new capability release before the kernel seam is stabilized

### Phase 62. Brainstack authoritative live-system state recall and cron capability-truth audit (INSERTED)

**Goal:** Make Brainstack authoritative about whether long-lived autonomous mechanisms such as heartbeat, pulse, and evolver are actually live now, while separately pinning down the cron file-write capability-truth boundary exposed by the latest pulse test.
**Status:** Completed
**Requirements**:
- stop treating old transcript/continuity narration as current autonomous-system truth
- represent current live-system state in Brainstack-owned operating truth
- keep live-state authority distinct from the Phase 61 recent-work recap lane
- close the cron no-write-tools incident with a precise evidence-backed ownership verdict
**Depends on:** Phase 61.1
**Plans:** 1 plan

Plans:
- [x] `62-01-PLAN.md` — Brainstack authoritative live-system state recall and cron capability-truth audit

Recommended next step:
- plan the post-62 architecture phase that removes task/operating hot-path dependence on remote structured-understanding without restoring heuristic routing

Recommended agent effort:
- `xhigh`

Planning note:
- accepted scope:
  - Brainstack-owned authority for current live-system state
  - demotion of stale transcript residue for "is it still running / working" questions
  - precise boundary verdict on the cron no-write-tools response
- rejected scope:
  - generic Hermes cron rewrite
  - broad filesystem permission cleanup unrelated to the evidence chain
  - phrase-table hacks for heartbeat/evolver/pulse queries
  - sidecar presence is not the design answer:
    - current live config has `sidecars.rtk.enabled: false`
    - the phase must not assume a missing sidecar is the root cause unless later evidence proves it
  - minimal host seam is allowed only if:
    - Brainstack cannot otherwise obtain authoritative current-state truth from existing runtime state
- rejected outcomes:
  - treating `session_search` timeout tuning as the main fix
  - hardcoding `phase 60`, `Brainstack`, `Tomi`, one Discord thread id, or one Hungarian phrasing as a special-case rescue
  - solving recap recall by shoving large raw transcript blocks into the ordinary memory packet
  - inventing a second memory owner beside Brainstack for "recent work"
  - generic Hermes `/resume` or session UX cleanup disguised as a Brainstack phase
  - locale-specific query farms or exact-phrase trigger tables
  - declaring success because session_search got faster while Brainstack recap recall still comes back empty

Execution result:
- Brainstack now has a typed current-state lane:
  - `live_system_state`
- source-of-truth changes landed in:
  - `brainstack/live_system_state.py`
  - `brainstack/operating_truth.py`
  - `brainstack/operating_context.py`
  - `brainstack/db.py`
  - `brainstack/__init__.py`
- current Hermes scheduler state now flows through:
  - operating-record listing
  - operating-record search
  - operating-context prompt projection
- explicit absence is now representable:
  - `No Hermes scheduler jobs are currently present in live runtime state.`
- the phase chose Brainstack-owned dynamic runtime-state projection over a new cron lifecycle host seam
- rebuilt runtime proof after final carry-forward:
  - `running healthy 0`
  - healthcheck `running; connected=discord`
- focused regression ring after final carry-forward:
  - `265 passed in 6.62s`
- bounded boundary verdict:
  - the cron file-write incident is currently classified as `false capability claim without tool attempt`

### Phase 63. Brainstack hot-path local typed understanding and remote-understanding demotion (INSERTED)

**Goal:** Replace mandatory remote `structured_understanding` authority in the ordinary Brainstack task/operating hot path with a local deterministic typed-understanding architecture that stays no-heuristic, multimodal-capable, and Brainstack-owned.
**Status:** Completed
**Requirements**:
- preserve the no-heuristic and no-rollback direction from Phase `61.1`
- keep Phase `62` live-state authority separate from ordinary task/operating route replacement
- remove mandatory remote-understanding dependence from ordinary task/operating read and capture behavior
- define a local typed substrate for hot-path understanding that does not collapse into text cue routing
- leave any remaining model-based understanding only as bounded off-path enrichment if execution can justify it
**Depends on:** Phase 62
**Plans:** 1 plan

Plans:
- [x] `63-01-PLAN.md` — Brainstack hot-path local typed understanding and remote-understanding demotion

Recommended next step:
- if a follow-up is needed, keep it narrow:
  - broaden local typed substrates and multimodal explicit envelopes without reintroducing remote hot-path authority
  - do not reopen heuristic routing or rollback paths

Recommended agent effort:
- `xhigh`

Planning note:
- accepted scope:
  - Brainstack-owned replacement of mandatory remote-understanding authority in ordinary task/operating reads
  - Brainstack-owned replacement of mandatory remote-understanding authority in ordinary task/operating capture
  - definition of a local typed substrate that can carry that authority
  - explicit demotion of remote understanding to bounded off-path use, if any use remains
- rejected scope:
  - rollback to `v1.0.16`
  - heuristic routing restoration under any new name
  - generic Hermes runtime/provider cleanup
  - moving the same classifier dependency into a hidden host helper
  - transcript/tool fallback presented as if the memory kernel itself had been fixed
- rejected outcomes:
  - better timeout behavior while hot-path authority still depends on remote understanding
- a text-only replacement architecture that quietly breaks the multimodal requirement
- local "rules" that are really just cue farms with different branding

### Phase 63.1. Brainstack durable policy canon, memory-plane separation, and non-governor boundary (INSERTED)

**Goal:** Make Brainstack the canonical durable store and projection layer for explicit user/project rules and memory-plane roles without turning the memory kernel into a runtime governor.
**Status:** Completed
**Requirements**:
- create a Brainstack-owned canonical policy/preference lane for explicit durable user and project rules
- separate procedural skill memory, durable policy memory, operating/live-state memory, and transcript/continuity evidence by role
- stop relying on transcript residue, native-memory spillover, or ad hoc skills as the only durable authority for cross-session engineering rules
- freeze the anti-rule that the memory kernel cannot become the scheduler, executor, or approval governor
- produce a read-only runtime-facing policy snapshot contract that a later runtime phase can consume without giving Brainstack governance ownership
**Depends on:** Phase 63
**Plans:** 1 plan

Plans:
- [x] `63.1-01-PLAN.md` — Brainstack durable policy canon, memory-plane separation, and non-governor boundary

Recommended next step:
- execute Phase 64 only after accepting that Brainstack now exposes canonical policy as read-only authority and still does not own runtime governance

Recommended agent effort:
- `xhigh`

Planning note:
- accepted scope:
  - Brainstack-owned canonical durable policy/preference storage
  - explicit memory-plane role separation
  - promotion and demotion rules for what may become durable authority
  - a runtime-facing read-only policy snapshot contract
- rejected scope:
  - turning Brainstack into the runtime governor
  - runtime execution, cron intake, or approval enforcement
  - transcript scraping as the main memory authority
  - "save everything" memory behavior
  - replacing procedural skills with policy records

Execution result:
- source-of-truth changes landed in:
  - `brainstack/__init__.py`
  - `brainstack/operating_truth.py`
  - `brainstack/operating_context.py`
- Brainstack now exposes canonical durable policy through:
  - `canonical_policy` operating records
  - `canonical_policy_snapshot()`
  - operating-context projection
- promotion is explicit-only:
  - no transcript-importance inference
  - no assistant-recap promotion
  - no heuristic importance engine
- the practical authority model is now frozen as:
  - `canonical policy`
  - `operating/live state`
  - `evidence`
  - with `skill` and native memory as support stores, not equal-authority policy lanes
- runtime-facing handoff remains read-only
- the non-governor boundary remains explicit
- carry-forward proof:
  - source `py_compile`: pass
  - isolated provider proof: pass
  - live checkout plugin compile/probe: pass
  - running container not restarted in this phase

### Phase 64. Runtime session-start intake, inbox contract, approval-gated proactive execution, and Brainstack handoff (INSERTED)

**Goal:** Define the Hermes runtime-side complement to Brainstack so proactive, entity-like behavior can emerge from explicit session-start intake and approval-gated execution rather than narrative claims or hidden heuristics.
**Status:** Completed
**Requirements**:
- preserve the Brainstack vs runtime ownership boundary established through Phases `61.1` to `63`
- define a typed JSON inbox-task contract rather than natural-language task inference
- make session-start recovery deterministic, bounded, and reusable
- define an approval gate for unfamiliar or blocked domains without heuristic routing
- ensure execution outcomes write back into typed durable state rather than transcript residue
**Depends on:** Phase 63.1
**Plans:** 1 plan

Plans:
- [x] `64-01-PLAN.md` — Runtime session-start intake, inbox contract, approval-gated proactive execution, and Brainstack handoff

Recommended next step:
- if broader autonomous execution is still desired, plan it as a separate runtime phase on top of the now-landed intake/writeback path instead of extending Brainstack ownership

Recommended agent effort:
- `xhigh`

Planning note:
- accepted scope:
  - runtime-side intake ordering
  - explicit inbox task schema
  - approval-gated execution model
  - typed writeback contract
  - reusable proactive runtime pattern
- rejected scope:
  - turning Brainstack into the scheduler
  - transcript fishing as a substitute for explicit task state
  - keyword-based domain gating
  - fake “always on” daemon semantics
  - Bestie-only folder conventions presented as architecture

Execution result:
- the runtime intake/writeback slice landed:
  - runtime-side explicit inbox consumer
  - read-only canonical policy/session-start handoff injection
  - Brainstack-seam mirroring for typed runtime handoff tasks
  - exact `task_id` projection in the session-start block
  - explicit `runtime_handoff_update` provider tool
  - inbox/outbox task lifecycle writeback
  - approval-required task blocking when `approved_by` is absent
- the execute cut did **not** turn Brainstack into a scheduler, executor, or approval governor
- paired live stabilizations also landed:
  - Tier-2 `400 Invalid input` request-contract fix
  - startup compression hot-path bounding
  - import-safe `web_tools` metadata that no longer triggers credential-pool lookup during builtin tool discovery
- proof after the final rebuild:
  - runtime handoff targeted suite: `5 passed`
  - broader regression ring: `324 passed`
  - rebuilt live container: `healthy`
  - restart count: `0`
  - container writeback probes:
    - auto-approved wiki task completed into `outbox`
    - high-risk alert blocked without approval
  - post-rebuild log scan: no new Tier-2 `400 Invalid input` lines and no new `Agent idle for 120s` cached-turn stalls

### Phase 999.1: deferred proactive continuity residual (BACKLOG)

**Goal:** Park the remaining proactive continuity residual as much-later technical debt instead of treating it as an active host-prompt micro-fix thread.
**Requirements:** TBD
**Plans:** 0 plans

Plans:
- [ ] TBD (promote with /gsd-review-backlog when ready)

### Phase 999.2: deferred tier2 intelligent extraction and contradiction weighting uplift (BACKLOG)

**Goal:** Park the later Tier-2 intelligence uplift as technical debt until it becomes a real product need, instead of smuggling it into correctness or donor-boundary phases.
**Requirements:** TBD
**Plans:** 0 plans

Plans:
- [ ] TBD (promote with /gsd-review-backlog when ready)

Planning note:
- this backlog item is about later Brainstack-owned Tier-2 capability uplift, not about donor transplant
- target technologies:
  - broader implicit preference extraction beyond the current narrow communication lane
  - more general correction-to-durable-rule extraction
  - targeted contradiction / supersession checks on identity and preference updates
  - richer decay / weighting sophistication for durable memory salience
- any future execution must stay:
  - bounded
  - session-end / scheduled where possible
  - token-disciplined
  - Brainstack-owned
- it must not create a second truth owner or a broad always-on inference tax

### Phase 65: Brainstack strict memory-kernel doctor and query inspect surface

**Goal:** Make Brainstack prove what memory-kernel state exists and why a query did or did not use it before changing retrieval behavior.
**Status:** Completed
**Requirements**:
- explicitly check the GSD Planning Enforcement section in `IMMUTABLE-PRINCIPLES.md` before planning or execution
- expose requested vs active graph/corpus/Tier-2 capabilities, backend error reasons, row counts, last writes, and last Tier-2 schedule/result state
- add a read-only query inspect surface that reports route, selected channels, selected evidence, suppressed evidence, and final rendered packet shape
- make degraded backend or extraction state explicit; do not allow "green" health when requested kernel capabilities are inactive
- keep doctor/inspect read-only and avoid turning Brainstack into a scheduler, executor, approval governor, or hidden runtime replacement
**Depends on:** Phase 64
**Plans:** 1 plan

Plans:
- [x] `65-01-PLAN.md` — Brainstack strict memory-kernel doctor and query inspect surface

Planning note:
- This is observability and proof infrastructure, not a retrieval improvement phase.
- Anti-goals:
  - no benchmark-specific fixes
  - no route or capture heuristic additions
  - no PR feature work before the kernel can explain itself
- Execution proof:
  - strict doctor and query inspect implemented
  - inspect path is read-only for retrieval telemetry
  - focused diagnostic tests passed by manual runner because `pytest` is not installed in this checkout

### Phase 66: Brainstack golden recall eval harness and regression gate

**Goal:** Create a fixed write-to-recall proof suite that measures whether durable Brainstack evidence is written, retrieved, attributed, and rendered correctly across sessions.
**Status:** Completed
**Requirements**:
- cover profile identity/preference, task, operating state, graph state/relation, corpus/document, temporal validity, cross-session recall, and paraphrase recall
- assert evidence id, source shelf, principal scope, provenance, and authority class, not just answer text
- include negative cases where unsupported memory-only answers must not be produced
- run without mandatory external LLM calls by using existing typed writes, fake Tier-2 seams, or local fixtures where needed
- record current failures honestly as baseline gaps, then convert fixed cases into regression gates
**Depends on:** Phase 65
**Plans:** 1 plan

Plans:
- [x] `66-01-PLAN.md` — Brainstack golden recall eval harness and regression gate

Execution proof:
- `scripts/brainstack_golden_recall_eval.py` added
- 6 hard-gated write-to-recall scenarios pass
- unsupported-query memory truth behavior remains expected-red and assigned to Phase 67/75

Planning note:
- This phase defines what "memory works" means in measurable terms.
- Anti-goals:
  - no answer-string-only smoke tests
  - no tests that pass while evidence attribution is wrong or absent
  - no reliance on live provider luck for the core regression gate

### Phase 67: Brainstack typed semantic evidence index for durable shelves

**Goal:** Add a typed semantic retrieval substrate over durable Brainstack shelves so paraphrase recall can work without keyword farms, locale phrase lists, or mandatory remote hot-path understanding.
**Status:** Completed
**Requirements**:
- index durable profile, task, operating, graph, continuity, transcript, and corpus records with stable record keys, shelf identity, owner, provenance, authority, and supersession metadata
- keep SQLite/authoritative durable records as source of truth; the semantic index is a retrieval aid, not a second truth owner
- support idempotent update, deletion, and supersession handling without duplicate evidence spam
- retrieve semantically related records across paraphrases without query-specific cue lists or language-specific keyword farms
- preserve multimodal-safe typed evidence contracts for future non-text records
- detect stale derived indexes when embedder, normalizer, chunker, schema, or source shelf version changes
**Depends on:** Phase 66
**Plans:** 1 plan

Plans:
- [x] `67-01-PLAN.md` — Brainstack typed semantic evidence index for durable shelves

Planning note:
- This is the structural answer to lexical-only recall failures.
- Anti-goals:
  - no renamed heuristic routing layer
  - no remote LLM dependency in the ordinary hot path
  - no raw transcript stuffing as a substitute for typed durable evidence
- Execution proof:
  - derived semantic evidence index added for authoritative shelves
  - write-path refresh and explicit backfill supported
  - stale fingerprint detection visible through doctor and excluded from search
  - Phase 66 golden hard gates still pass

### Phase 68: Brainstack Tier-2 execution reliability and bounded durable promotion

**Goal:** Make Tier-2 extraction scheduling, execution, parsing, write counts, no-op reasons, and promotion boundaries observable and reliable without widening the hot-path inference tax.
**Status:** Completed
**Requirements**:
- surface Tier-2 batch size, trigger reason, parse status, emitted counts, write counts, no-op reasons, and failure events through the Phase 65 inspect/doctor surface
- define bounded idle/session-end/user-turn flush policy that cannot hang the runtime or silently disappear
- preserve provenance and prevent assistant-authored self-diagnosis from contaminating user-owned durable truth
- promote only explicit or high-confidence durable evidence through typed schemas; do not introduce a broad importance engine
- prove reliability improvements against Phase 66 golden evals and explicit extraction failure scenarios
**Depends on:** Phase 67
**Plans:** 1 plan

Plans:
- [x] `68-01-PLAN.md` — Brainstack Tier-2 execution reliability and bounded durable promotion

Planning note:
- This phase fixes the "Tier-2 probably ran" ambiguity.
- Anti-goals:
  - no always-on broad extraction tax
  - no assistant-message truth promotion shortcut
  - no hidden fallback that makes failed extraction look successful
- Execution proof:
  - durable Tier-2 run records added
  - latest persistent run visible through doctor
  - assistant-authored Tier-2 candidates rejected before durable truth promotion
  - Phase 66 golden hard gates still pass

### Phase 69: Brainstack graph recall honesty, semantic seed, and naming correction

**Goal:** Make graph memory recall honest and useful by either explicitly naming the current lexical graph behavior or adding typed semantic/alias seeding before graph expansion.
**Status:** Completed
**Requirements**:
- separate Kuzu graph storage health from graph recall semantics in doctor and inspect output
- label current graph recall mode accurately if it remains lexical `CONTAINS` seeding
- if Phase 67 provides a typed semantic evidence index, use it as the bounded seed source for graph entity/state/relation expansion
- prove graph paraphrase, alias, state, and relation recall through Phase 66 golden evals
- avoid importing an unrelated graph-memory framework or building a Graphiti clone inside this phase
**Depends on:** Phase 68
**Plans:** 1 plan

Plans:
- [x] `69-01-PLAN.md` — Brainstack graph recall honesty, semantic seed, and naming correction

Planning note:
- This phase prevents the graph layer from being oversold as semantic memory when it is only lexical expansion.
- Anti-goals:
  - no graph-side keyword farm
  - no broad ontology project
  - no external donor transplant without Brainstack-owned contracts
- Execution proof:
  - graph storage health and graph recall mode are reported separately
  - query inspect exposes `graph_recall` with `lexical_seeded`, `semantic_seeded`, or `hybrid_seeded`
  - typed semantic graph seeds resolve through the Phase 67 semantic evidence index
  - Phase 66 golden recall now has 7 hard gates, including `graph.semantic_seed_state`
  - lexical-only graph recall is explicitly tested and labelled honestly

### Phase 70: Brainstack agent-facing memory tool surface

**Goal:** Add a focused Brainstack-owned model-facing memory tool surface so Hermes agents can recall, inspect, and understand memory state first, with write-like tools gated behind the later explicit durable capture contract.
**Status:** Completed
**Requirements**:
- explicitly check `IMMUTABLE-PRINCIPLES.md` and `.planning/research/external-memory-donor-source-map.md` before planning or execution
- adapt the proven provider-tool pattern from Mnemosyne `hermes_memory_provider/__init__.py`, CerebroCortex `HERMES_INTEGRATE.md`, and neural-memory tool separation without copying their authority model blindly
- expose read-only memory-kernel tools first, especially `brainstack_recall`, `brainstack_inspect`, and `brainstack_stats`
- keep `brainstack_remember`, `brainstack_supersede`, and `brainstack_invalidate` disabled or schema-only until Phase 72 has frozen the explicit durable capture contract
- route every write through Brainstack typed shelf contracts with principal scope, provenance, authority class, evidence id, and supersession metadata
- enforce an explicit model-facing allowlist vs operator/debug-only tool split so MCP availability does not imply normal model-callability
- keep tools transparent in Phase 65 inspect output and covered by Phase 66 golden recall/evidence gates
- reject scheduler, executor, approval, messaging, or hidden task-governor tools in this phase
**Depends on:** Phase 69
**Plans:** 1 plan

Plans:
- [x] `70-01-PLAN.md` — Brainstack agent-facing memory tool surface

Planning note:
- This is the main answer to the Mnemosyne/CerebroCortex product-surface gap.
- Source patterns:
  - https://github.com/AxDSan/mnemosyne/blob/main/hermes_memory_provider/__init__.py
  - https://github.com/buckster123/CerebroCortex/blob/main/HERMES_INTEGRATE.md
  - https://github.com/itsXactlY/neural-memory
- Anti-goals:
  - no broad MCP tool jungle
  - no direct transcript-to-truth shortcut
  - no tool that can make Brainstack execute work or enforce approval
- Execution proof:
  - `brainstack_recall`, `brainstack_inspect`, and `brainstack_stats` are exposed as read-only provider tools
  - write-like memory tools were gated at Phase 70 closeout; Phase 72 now enables `brainstack_remember` and `brainstack_supersede` through schema contracts
  - `runtime_handoff_update` is operator-only by default and not exported through the normal model-callable memory tool surface
  - recall tool returns selected evidence without mutating profile truth
  - Phase 66 golden recall still passes 7 hard gates

### Phase 71: Brainstack provider lifecycle and MCP/operator UX

**Goal:** Make Brainstack feel like a practical, drop-in Hermes memory provider by hardening lifecycle hooks, operator health/status UX, and optional MCP/CLI access without increasing host patch surface.
**Status:** Completed
**Requirements**:
- explicitly check `IMMUTABLE-PRINCIPLES.md` and `.planning/research/external-memory-donor-source-map.md` before planning or execution
- adapt Mnemosyne-style provider lifecycle concepts: system prompt block, pre-turn prefetch, post-turn sync, session-end maintenance hook, and builtin-memory mirror hook only where Brainstack authority rules allow it
- adapt CerebroCortex's split between MCP tools and provider plugin as an optional UX pattern, not as a parallel host architecture
- surface provider availability, configured-vs-active capabilities, exported tools, lifecycle hook status, and latency through Phase 65 doctor/inspect
- define shared-state concurrency, locking/resync, and degraded-state behavior when provider and optional MCP/operator access touch the same Brainstack state
- preserve Hermes as runtime owner and keep Brainstack logic inside Brainstack provider/adapter boundaries
- prove activation and tool export against the latest Hermes checkout at `/home/lauratom/Asztal/ai/veglegeshermes-source`
**Depends on:** Phase 70
**Plans:** 1 plan

Plans:
- [x] `71-01-PLAN.md` — Brainstack provider lifecycle and MCP/operator UX

Planning note:
- This phase is product ergonomics and host-seam discipline, not a retrieval algorithm phase.
- Source patterns:
  - https://github.com/AxDSan/mnemosyne/blob/main/hermes_memory_provider/__init__.py
  - https://github.com/buckster123/CerebroCortex/blob/main/HERMES_INTEGRATE.md
- Anti-goals:
  - no Hermes rewrite
  - no new mandatory always-on daemon
  - no plugin mechanism that hides degraded provider state
- Execution proof:
  - provider lifecycle status reports `active`, `degraded`, or `unavailable`
  - lifecycle hook status and exported tools are visible through `brainstack_stats`
  - operator-only tools are visible separately from model-callable exported tools
  - disabled memory write-like tools remain visible as disabled, not silently callable; Phase 72 later enables only the contracted remember/supersede subset
  - shared-state safety states API-only operator access and no direct DB mutation
  - Phase 66 golden recall still passes 7 hard gates

### Phase 72: Brainstack explicit durable capture contract

**Goal:** Add a deterministic, multilingual-safe explicit durable capture path for user-owned facts, profile updates, project state, procedures, and corrections without resurrecting Tier-1 keyword farms.
**Status:** Completed
**Requirements**:
- explicitly check `IMMUTABLE-PRINCIPLES.md` and `.planning/research/external-memory-donor-source-map.md` before planning or execution
- use Phase 70 tools and Brainstack typed schemas as the primary explicit write path instead of language-specific "remember that" regex matching
- support durable capture fields for shelf target, principal scope, authority class, validity window, source evidence, supersession intent, and confidence
- preserve Hermes/native explicit truth ownership where applicable; Brainstack may mirror or project only through reviewed seams
- include multilingual golden cases in Phase 66 style fixtures rather than English/Hungarian-only cue lists
- emit inspectable no-op reasons when a candidate is rejected or requires runtime/user confirmation
**Depends on:** Phase 71
**Plans:** 1 plan

Plans:
- [x] `72-01-PLAN.md` — Brainstack explicit durable capture contract

Planning note:
- This phase is the non-heuristic replacement for the current empty Tier-1/product capture gap.
- Source patterns:
  - Mnemosyne `mnemosyne_remember` scope/validity/write affordance
  - CerebroCortex provider background sync, but only where typed evidence and authority allow it
- Anti-goals:
  - no keyword-farm live capture
  - no assistant-authored recap promotion
  - no one-live-case memory patching
- Execution proof:
  - `brainstack_remember` and `brainstack_supersede` are enabled only through explicit typed schemas
  - `brainstack_invalidate` remains disabled; Phase 73 later enables `brainstack_consolidate` only as bounded maintenance
  - assistant-authored and insufficient payloads return rejection receipts and do not write truth
  - profile supersession updates the stable-key row without duplicate truth spam
  - multilingual profile capture works through schema payloads, not phrase matching
  - operating and task captures route through typed shelf fields
  - Phase 66 golden recall still passes 7 hard gates

### Phase 73: Brainstack bounded memory maintenance lifecycle

**Goal:** Add explicit, inspectable memory maintenance for dedupe, supersession cleanup, stale evidence handling, conflict hygiene, and bounded consolidation without adopting unbounded dream-engine behavior.
**Status:** Completed
**Requirements**:
- explicitly check `IMMUTABLE-PRINCIPLES.md` and `.planning/research/external-memory-donor-source-map.md` before planning or execution
- adapt Mnemosyne `sleep` and neural-memory/CerebroCortex consolidation ideas into Brainstack-owned maintenance jobs with strict budgets, dry-run output, and inspectable receipts
- maintain shelf authority: consolidation may merge, downrank, supersede, or summarize only under explicit typed rules and with preserved provenance
- support manual tool-triggered maintenance and safe session-end/idle scheduling through Hermes runtime boundaries, not Brainstack-owned scheduling
- expose maintenance candidate counts, changes, no-op reasons, latency, and errors through doctor/inspect
- prove no durable truth is lost through Phase 66 regression gates
**Depends on:** Phase 72
**Plans:** 1 plan

Plans:
- [x] `73-01-PLAN.md` — Brainstack bounded memory maintenance lifecycle

Planning note:
- This phase may use the word consolidation, not "dream", unless the implementation is literally a bounded maintenance pipeline.
- Source patterns:
  - https://github.com/AxDSan/mnemosyne/blob/main/hermes_memory_provider/__init__.py
  - https://github.com/itsXactlY/neural-memory
  - https://github.com/buckster123/CerebroCortex/blob/main/HERMES_INTEGRATE.md
- Anti-goals:
  - no autonomous hidden reasoning loop
  - no broad salience engine before evidence correctness
  - no summarization that destroys source evidence ids
- Execution proof:
  - `brainstack_consolidate` is enabled as dry-run-first bounded maintenance
  - dry-run reports semantic-index, profile-duplicate, and graph-conflict candidates
  - apply mode supports only derived `semantic_index` rebuild
  - unsupported apply classes reject with no-op reasons and no mutation
  - tests prove durable profile truth row counts are preserved
  - Phase 66 golden recall still passes 7 hard gates

### Phase 74: Brainstack session and procedure memory read-model

**Goal:** Add memory-safe session/procedure support so Brainstack can recall how work is normally done and what session state exists, while Hermes runtime remains responsible for execution, scheduling, and approval.
**Status:** Completed
**Requirements**:
- explicitly check `IMMUTABLE-PRINCIPLES.md` and `.planning/research/external-memory-donor-source-map.md` before planning or execution
- adapt CerebroCortex session/procedure memory concepts only as recallable typed records and read-only projections, not as agent workflow ownership
- represent procedure memory as durable "how to work" knowledge with provenance, scope, and versioning; do not replace Codex skills or Hermes runtime policies
- represent session state as bounded continuity/state evidence with explicit owner and expiration rules
- expose procedure/session hits in inspect output and require evidence ids in golden evals
- reject intention, todo, messaging, or action tools that would make Brainstack a hidden runtime coordinator
**Depends on:** Phase 73
**Plans:** 1 plan

Plans:
- [x] `74-01-PLAN.md` — Brainstack session and procedure memory read-model
- [x] `74-PROCEDURE-SESSION-CONTRACT.md` — read-model-only procedure/session contract
- [x] `74-EXECUTION-RESULT.md` — implementation summary
- [x] `74-PROOF.md` — verification evidence

Planning note:
- This phase extracts the useful part of CerebroCortex's agent-work helper idea while enforcing the non-governor principle.
- Source patterns:
  - https://github.com/buckster123/CerebroCortex/blob/main/HERMES_INTEGRATE.md
  - https://github.com/buckster123/CerebroCortex/blob/main/src/cerebro/cortex.py
- Anti-goals:
  - no scheduler
  - no executor
  - no approval governor
  - no duplicate procedural-skill system

Completion proof:
- `procedure_memory` and `session_state` operating record types added
- expired `session_state` records are suppressed from list, keyword, semantic, and local-probe recall
- volatile session-state relevance guard prevents unrelated active session state from surfacing on a different expired-state query
- focused Phase 74 tests passed 2/2
- regression runner passed 28/28 runnable tests
- Phase 66 golden recall still passes 7 hard gates

### Phase 75: Brainstack bounded associative expansion and activation ranking

**Goal:** Add bounded associative graph expansion and activation-style ranking on top of Phase 67/69 semantic seeds so Brainstack can find related memory through relations, aliases, context ids, and multi-hop evidence without opaque graph magic.
**Status:** Completed
**Requirements**:
- explicitly check `IMMUTABLE-PRINCIPLES.md` and `.planning/research/external-memory-donor-source-map.md` before planning or execution
- adapt CerebroCortex recall pipeline concepts and neural-memory `think`/spreading activation only as a bounded candidate expansion/ranking stage
- do not start behavior-changing packet inclusion until Phase 67/69 have proven typed semantic seeds, graph recall mode honesty, and false-positive controls
- require max depth, max candidate count, cost budget, channel authority, and trace explanation for every expansion
- preserve current-state and authoritative profile/operating evidence above associative volume
- keep original evidence records for final packet output; embeddings or compressed text may be used only for retrieval/ranking
- prove paraphrase, alias, relation, and false-positive controls through Phase 66 evals
**Depends on:** Phase 74
**Plans:** 1 plan

Plans:
- [x] `75-01-PLAN.md` — Brainstack bounded associative expansion and activation ranking
- [x] `75-ASSOCIATIVE-EXPANSION-CONTRACT.md` — bounded graph expansion contract
- [x] `75-EXECUTION-RESULT.md` — implementation summary
- [x] `75-PROOF.md` — verification evidence

Planning note:
- This phase should feed the later fused retrieval and allocator candidates; it must not become an ontology project.
- Source patterns:
  - https://github.com/buckster123/CerebroCortex/blob/main/src/cerebro/cortex.py
  - https://github.com/itsXactlY/neural-memory/blob/master/python/neural_memory.py
  - https://github.com/EveryOneIsGross/defaultmodeAGENT/blob/main/agent/hippocampus.py
- Anti-goals:
  - no unbounded spreading activation
  - no hidden rerank farm
  - no authority-blind semantic similarity scoring

Completion proof:
- bounded graph-only associative expansion added with seed/depth/candidate/search/shelf limits
- inspect output exposes expansion seeds, anchors, hops, included candidates, suppressed candidates, and cost
- relation/context expansion can find linked graph state through an alias-style edge
- superficially related linked state is suppressed with an inspectable reason
- focused Phase 75 tests passed 3/3
- regression runner passed 31/31 runnable tests
- Phase 66 golden recall now passes 8 hard gates, including `graph.associative_alias_state`

### Phase 76: Brainstack product-grade corpus ingest substrate

**Goal:** Turn large knowledge storage into a product-grade Brainstack corpus subsystem with stable source adapters, sectioning, hashing, idempotent re-ingest, citations, and bounded recall across local knowledge bodies.
**Status:** Completed
**Requirements**:
- explicitly check `IMMUTABLE-PRINCIPLES.md` and `.planning/research/external-memory-donor-source-map.md` before planning or execution
- generalize the deferred wiki/environment-note idea into a corpus ingest substrate instead of a special prompt-injection path or one-off source shelf
- support source adapters, document normalization, section identity, content hash, provenance, authority, principal scope, and citation/evidence id projection
- keep raw document bodies out of prompts unless selected by bounded retrieval/fusion/allocation
- support idempotent update/delete/reindex without duplicate document spam
- detect corpus index drift when parser, sectioner, normalizer, embedder, source adapter, schema, or content hash changes
- add corpus-specific golden evals for citation correctness, stale document replacement, multilingual document recall, and large-knowledge token savings
**Depends on:** Phase 75
**Plans:** 1 plan

Plans:
- [x] `76-01-PLAN.md` — Brainstack product-grade corpus ingest substrate
- [x] `76-CORPUS-INGEST-CONTRACT.md` — typed corpus ingest contract
- [x] `76-EXECUTION-RESULT.md` — implementation summary
- [x] `76-PROOF.md` — verification evidence

Planning note:
- Competitors mostly pressure Brainstack on product UX here; Brainstack's own principle requires strong large-knowledge storage.
- This phase should supersede or absorb the current wiki-only PullPhase candidate when promoted.
- Anti-goals:
  - no raw wiki/file dumping
  - no uncontrolled file stuffing
  - no bypass around corpus budgets or provenance

Completion proof:
- typed corpus source normalizer and sectioner added
- idempotent corpus source ingest returns inserted/updated/unchanged receipts
- citation ids, document hashes, and section hashes are projected into corpus recall
- corpus ingest status reports stale/missing ingest metadata as degraded
- stale source content replacement preserves one document row and replaces sections/FTS
- focused Phase 76 tests passed 4/4
- regression runner passed 35/35 runnable tests
- Phase 66 golden recall now passes 10 hard gates, including corpus citation, multilingual, and token-budget cases

### Phase 77: Brainstack multilingual and multimodal proof gate

**Goal:** Convert the multilingual/multimodal principle from aspiration into a recurring proof gate across capture, semantic indexing, graph recall, corpus recall, tool surface, and final packet rendering.
**Status:** Completed
**Requirements**:
- explicitly check `IMMUTABLE-PRINCIPLES.md` and `.planning/research/external-memory-donor-source-map.md` before planning or execution
- add golden/e2e cases for at least Hungarian, English, German, and one non-Latin-script language across profile, graph relation, corpus, and explicit capture scenarios
- define typed evidence contracts for non-text-derived records such as image, file, audio, and extracted-document evidence without requiring full multimodal implementation in this phase
- reject language-specific phrase lists as the main intelligence layer; failures must drive semantic/index/contract improvements instead
- measure accuracy, token efficiency, and latency under the required priority order: accuracy > token efficiency > speed
- produce an explicit competitive-readiness scorecard against Mnemosyne, CerebroCortex, neural-memory, and Brainstack's own product-quality targets, backed by local proof or clearly marked as unsupported/deferred
**Depends on:** Phase 76
**Plans:** 1 plan

Plans:
- [x] `77-01-PLAN.md` — Brainstack multilingual and multimodal proof gate
- [x] `77-MULTILINGUAL-MULTIMODAL-CONTRACT.md` — language/modality proof contract
- [x] `77-EXECUTION-RESULT.md` — implementation summary
- [x] `77-PROOF.md` — verification evidence

Planning note:
- This phase is mostly a Brainstack principle gap, not a competitor transplant.
- It keeps the "massively #1" claim honest by forcing proof beyond English-only text-memory demos.
- Anti-goals:
  - no benchmark-only score chasing
  - no language-specific hack patches
  - no pretending multimodal support exists before typed contracts and evidence projection exist

Completion proof:
- golden hard gates now cover English, Hungarian, German, and non-Latin script
- non-Latin explicit capture recall is proven through `brainstack_remember`
- typed modality evidence contract added for image/file/audio/extracted-document references
- raw binary/base64 modality payloads are rejected
- multilingual/multimodal gate reports latency, max packet chars, language coverage, modality status, and scorecard
- focused Phase 77 tests passed 3/3
- regression runner passed 38/38 runnable tests
- Phase 66 golden recall now passes 14 hard gates

### Deferred PR/PullPhase candidate queue (NON-CANONICAL)

These PR/PullPhase items are intentionally not canonical phase numbers yet. They stay behind Phase 65-77 until the memory-kernel proof chain and competitor-informed product-surface phases are complete and the project is ready to promote PR integration work.

Promotion rule:
- Do not assign canonical phase numbers to these candidates until Phase 65-77 are complete and reviewed.
- Keep detailed candidate text in `PR-CANDIDATES.md` until promotion.
- When promoted, insert them after the then-current canonical memory-kernel sequence rather than assuming fixed numbers now.

#### PullPhase candidate 1: post-refactor traceable hybrid retrieval fusion

**Goal:** After the planned kernel/god-object refactor and reliability proof phases, turn Brainstack's keyword, semantic, graph, temporal, profile, operating, and corpus retrieval outputs into one traceable fused candidate ranking without adding query-specific heuristics.
**Status:** Deferred non-canonical candidate
**Requirements**:
- wait for the refactor to expose stable retriever/candidate/trace seams before detailed implementation planning
- depend on Phase 65-69 proof surfaces so fusion work cannot hide missing writes, degraded backends, lexical-only graph behavior, or Tier-2 failures
- define one common candidate contract for all shelves that can carry source channel, raw score, rank, authority, recency, provenance, and explanation fields
- preserve Brainstack-universal behavior only; do not tune for one live thread, one phrasing, one benchmark, or one user
- produce retrieval traces that explain why candidates won, lost, merged, or were suppressed
- keep authoritative profile/operating truth protected from being drowned by transcript/corpus volume

Planning note:
- This candidate is deliberately after the kernel proof chain, not before it.
- Expected post-refactor integration seams:
  - `RetrievalCandidate`
  - `Retriever` / shelf adapters
  - `FusionPolicy`
  - `RetrievalTrace`
- Anti-goals:
  - no giant rerank farm
  - no "turn Chroma on" non-solution
  - no opaque benchmark-tuned scoring

#### PullPhase candidate 2: post-refactor global working-memory allocator and packet budgeter

**Goal:** Replace fragmented shelf-local packet limits with a route-aware global working-memory allocator that selects the final rendered evidence packet by value, authority, cost, and route relevance.
**Status:** Deferred non-canonical candidate
**Requirements**:
- depends on the fused candidate ranking and traceability candidate
- allocate one global packet budget across profile, operating, continuity, transcript, graph, corpus, and other eligible shelves
- keep hard minimums for authoritative current truth, explicit user-owned facts, active task state, and conflict/current-state evidence
- cut low-value evidence before high-authority evidence, even when the low-value evidence came from a shelf with spare local capacity
- expose why each final packet item was included and why each rejected item was cut

Planning note:
- This candidate should not start from today's `evidence_item_budget` alone. It should start from the post-refactor packet assembly seam.
- Expected post-refactor integration seams:
  - `WorkingMemoryBudget`
  - `EvidenceCost`
  - `PacketAssembler`
  - route-aware minimum/maximum policy
- Anti-goals:
  - no prompt stuffing
  - no blind per-shelf caps pretending to be global allocation
  - no allocator that can silently drop authoritative operating/profile truth

#### PullPhase candidate 3: post-refactor wiki corpus source through bounded corpus ingest

**Goal:** Add wiki/environment-note knowledge as a normal bounded corpus ingestion source, not as a direct prompt-injection path or special memory shelf.
**Status:** Deferred non-canonical candidate
**Requirements**:
- depends on the refactored corpus ingest/index/retrieval seams being stable
- represent wiki content as corpus documents with stable keys, source metadata, page/title/path identity, content hash, and sectioning
- route all wiki recall through the existing corpus shelf and the future fusion/allocation path
- support idempotent re-ingest without duplicate document spam
- keep raw wiki bodies out of the system prompt unless selected by bounded retrieval

Planning note:
- This is intentionally lower risk than a new donor shelf. It should be a `doc_kind` / `source_type` expansion inside the corpus model.
- Expected post-refactor integration seams:
  - `CorpusIngestSource`
  - `DocumentNormalizer`
  - `CorpusDocument`
  - `CorpusIndexer`
- Anti-goals:
  - no raw wiki snippet dumping
  - no uncontrolled file stuffing
  - no bypass around corpus retrieval budgets

#### PullPhase candidate 4: post-refactor Hermes stable extension seams and installer patch reduction

**Goal:** Reduce Brainstack's Hermes host integration patch surface by moving patch-heavy installer behavior toward stable Hermes extension seams where the post-refactor architecture makes that practical.
**Status:** Deferred non-canonical candidate
**Requirements**:
- inventory every remaining host patch and classify it as stable seam candidate, temporary compatibility patch, or unavoidable host-owned behavior
- preserve Brainstack as a single external memory provider; do not build a parallel host architecture
- move provider registration, config, health/doctor, and tool-surface policy toward explicit seams where available
- keep source-of-truth Brainstack logic in Brainstack and latest host verification in `veglegeshermes-source`
- prove that patch reduction does not regress live install, doctor, gateway, or memory-provider activation

Planning note:
- This candidate is strategic maintenance, not a quick feature PR. It should not be mixed with retrieval, allocator, or corpus feature work.
- Expected post-refactor integration seams:
  - `HostIntegrationAdapter`
  - `MemoryProviderRegistration`
  - `ToolSurfacePolicy`
  - `RuntimeHealthContract`
- Anti-goals:
  - no local-only patch shortcuts
  - no "Brainstack needs to become a plugin" reframing
  - no broad Hermes rewrite disguised as Brainstack patch cleanup
