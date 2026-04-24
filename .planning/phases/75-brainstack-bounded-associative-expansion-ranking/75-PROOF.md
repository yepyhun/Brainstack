# Phase 75 Proof

## Verification Commands

```bash
cd /home/lauratom/Asztal/ai/atado/Brainstack-phase50
python3 -m py_compile brainstack/associative_expansion.py brainstack/executive_retrieval.py brainstack/control_plane.py brainstack/diagnostics.py tests/test_associative_expansion.py scripts/brainstack_golden_recall_eval.py
```

Result: PASS.

Focused Phase 75 tests:

```text
RUN 3
PASSED
```

Regression suite:

```text
RUN 31 tests
PASSED all runnable tests
```

Golden recall eval:

```text
schema=brainstack.golden_recall_eval.v1
verdict=pass
hard_gate=8 passed, 0 failed
baseline=2 scenarios, expected_red=negative.unsupported_query_has_no_memory_truth
pass: profile.exact_identity shelf=profile selected=1 reason=selected expected evidence
pass: task.exact_open_task shelf=task selected=2 reason=selected expected evidence
pass: operating.exact_active_work shelf=operating selected=1 reason=selected expected evidence
pass: corpus.exact_document_section shelf=corpus selected=1 reason=selected expected evidence
pass: graph.exact_state shelf=graph selected=1 reason=selected expected evidence
pass: graph.semantic_seed_state shelf=graph selected=1 reason=selected expected evidence
pass: graph.associative_alias_state shelf=graph selected=2 reason=selected expected evidence
pass: continuity.cross_session_match shelf=continuity_match selected=1 reason=selected expected evidence
baseline_pass: profile.paraphrase_semantic_gap shelf=profile selected=1 reason=selected expected evidence
expected_red: negative.unsupported_query_has_no_memory_truth shelf=- selected=3 reason=unsupported query selected memory evidence
```

## Gate Verdict

PASS.

- Related graph memory can be found through bounded relation/context expansion.
- Every expansion reports seeds, anchors, hops, included candidates, suppressed candidates, and cost.
- Superficially related connected state is suppressed.
- Authoritative profile truth remains selected when associative graph candidates are present.
- Existing golden recall hard gates still pass, now with one added Phase 75 hard gate.

