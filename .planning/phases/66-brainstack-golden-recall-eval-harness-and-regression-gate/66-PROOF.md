# Phase 66 Proof

## Verification Commands

```bash
cd /home/lauratom/Asztal/ai/atado/Brainstack-phase50
python3 -m py_compile scripts/brainstack_golden_recall_eval.py tests/test_golden_recall_eval.py
python3 scripts/brainstack_golden_recall_eval.py
```

Result:

```text
schema=brainstack.golden_recall_eval.v1
verdict=pass
hard_gate=6 passed, 0 failed
baseline=2 scenarios, expected_red=negative.unsupported_query_has_no_memory_truth
pass: profile.exact_identity shelf=profile selected=1 reason=selected expected evidence
pass: task.exact_open_task shelf=task selected=2 reason=selected expected evidence
pass: operating.exact_active_work shelf=operating selected=1 reason=selected expected evidence
pass: corpus.exact_document_section shelf=corpus selected=1 reason=selected expected evidence
pass: graph.exact_state shelf=graph selected=1 reason=selected expected evidence
pass: continuity.cross_session_match shelf=continuity_match selected=1 reason=selected expected evidence
baseline_pass: profile.paraphrase_semantic_gap shelf=profile selected=1 reason=selected expected evidence
expected_red: negative.unsupported_query_has_no_memory_truth shelf=- selected=2 reason=unsupported query selected memory evidence
```

```bash
cd /home/lauratom/Asztal/ai/atado/Brainstack-phase50
python3 - <<'PY'
import importlib.util
import sys
from pathlib import Path

root = Path.cwd()
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location("test_golden_recall_eval", root / "tests/test_golden_recall_eval.py")
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)
for name in [
    "test_golden_recall_hard_gates_pass",
    "test_golden_recall_records_baseline_gaps_without_failing",
]:
    getattr(mod, name)()
PY
```

Result: PASS.

Note: `pytest` is not installed in this checkout, so pytest-compatible tests were executed through a manual runner.

## Gate Verdict

PASS for Phase 66 scope.

The suite proves durable write-to-recall attribution for six hard-gated shelves and reports current unsupported-query behavior as an expected-red gap instead of hiding it.
