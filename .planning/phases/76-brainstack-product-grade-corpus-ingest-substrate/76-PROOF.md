# Phase 76 Proof

## Verification Commands

```bash
cd /home/lauratom/Asztal/ai/atado/Brainstack-phase50
python3 -m py_compile brainstack/corpus_ingest.py brainstack/db.py brainstack/retrieval.py brainstack/diagnostics.py tests/test_corpus_ingest_substrate.py scripts/brainstack_golden_recall_eval.py
```

Result: PASS.

Focused Phase 76 tests:

```text
RUN 4
PASSED
```

Regression suite:

```text
RUN 35 tests
PASSED all runnable tests
```

Golden recall eval:

```text
schema=brainstack.golden_recall_eval.v1
verdict=pass
hard_gate=10 passed, 0 failed
baseline=2 scenarios, expected_red=negative.unsupported_query_has_no_memory_truth
pass: profile.exact_identity shelf=profile selected=1 reason=selected expected evidence
pass: task.exact_open_task shelf=task selected=2 reason=selected expected evidence
pass: operating.exact_active_work shelf=operating selected=1 reason=selected expected evidence
pass: corpus.exact_document_section shelf=corpus selected=1 reason=selected expected evidence
pass: corpus.multilingual_hungarian shelf=corpus selected=1 reason=selected expected evidence
pass: corpus.large_doc_token_budget shelf=corpus selected=2 reason=selected expected evidence
pass: graph.exact_state shelf=graph selected=1 reason=selected expected evidence
pass: graph.semantic_seed_state shelf=graph selected=1 reason=selected expected evidence
pass: graph.associative_alias_state shelf=graph selected=2 reason=selected expected evidence
pass: continuity.cross_session_match shelf=continuity_match selected=1 reason=selected expected evidence
baseline_pass: profile.paraphrase_semantic_gap shelf=profile selected=1 reason=selected expected evidence
expected_red: negative.unsupported_query_has_no_memory_truth shelf=- selected=3 reason=unsupported query selected memory evidence
```

## Gate Verdict

PASS.

- Corpus documents can be ingested and re-ingested without duplicates.
- Recall returns citation ids, document hashes, and section hashes.
- Stale legacy corpus ingest metadata is explicitly degraded.
- Changed source content replaces stale sections safely.
- Large documents are not raw-dumped into prompts; selected sections are bounded by corpus budget.
- Existing golden recall hard gates still pass, now with corpus citation/multilingual/token gates.

