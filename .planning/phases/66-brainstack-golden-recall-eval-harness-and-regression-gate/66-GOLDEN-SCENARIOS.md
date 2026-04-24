# Phase 66 Golden Recall Scenario Matrix

## Hard Gates

These cases must pass before later retrieval/index changes are accepted:

- `profile.exact_identity`: profile fixture write is selected with shelf `profile`, stable key `identity:name`, source `golden_fixture`.
- `task.exact_open_task`: task fixture write is selected with shelf `task`, stable key `task:phase66:golden-proof`, source `golden_fixture`.
- `operating.exact_active_work`: operating fixture write is selected with shelf `operating`, stable key `operating:phase66:active-work`, source `golden_fixture`.
- `corpus.exact_document_section`: corpus fixture section is selected with shelf `corpus`, source `golden_fixture`.
- `graph.exact_state`: graph state fixture is selected with shelf `graph`, source `golden_fixture`, and the packet preview contains the expected state value.
- `continuity.cross_session_match`: continuity fixture survives store reopen and is selected with shelf `continuity_match`, source `golden_fixture`.

## Baseline / Expected-Red

These are measured but do not fail Phase 66:

- `profile.paraphrase_semantic_gap`: currently baseline-pass. Phase 67 owns robust typed semantic/paraphrase behavior.
- `negative.unsupported_query_has_no_memory_truth`: expected-red. Current packet policy may include generally authoritative evidence for unsupported queries. Phase 67/75 own ranking and suppression improvements.

## Scope Guard

The harness does not add route logic, capture logic, keyword cues, locale phrase lists, or retrieval ranking behavior. It only writes typed fixtures, reopens the store, runs Phase 65 query inspect, and asserts evidence attribution.
