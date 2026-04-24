# Phase 65 Proof

## Verification Commands

```bash
cd /home/lauratom/Asztal/ai/atado/Brainstack-phase50
python3 -m py_compile brainstack/diagnostics.py brainstack/control_plane.py brainstack/__init__.py tests/test_diagnostics.py
```

Result: PASS.

```bash
cd /home/lauratom/Asztal/ai/atado/Brainstack-phase50
python3 - <<'PY'
import importlib.util
import sys
import tempfile
from pathlib import Path

root = Path.cwd()
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location("test_diagnostics", root / "tests/test_diagnostics.py")
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

for name in [
    "test_strict_doctor_fails_when_requested_external_backends_are_missing",
    "test_sqlite_only_doctor_reports_active_honest_capabilities",
    "test_query_inspect_is_read_only_for_retrieval_telemetry",
]:
    with tempfile.TemporaryDirectory() as td:
        getattr(mod, name)(Path(td))
PY
```

Result: PASS.

Note: `python3 -m pytest tests/test_diagnostics.py -q` could not run in this checkout because `pytest` is not installed (`No module named pytest`). The same test functions were executed by the manual runner above.

## Real-World Proof Sample

Scenario:

- Write one principal-scoped profile fact.
- Run strict doctor in SQLite-only mode.
- Run query inspect for a matching query.
- Verify the selected evidence appears in the rendered packet preview and no selected profile evidence is mislabeled as suppressed.

Observed proof summary:

```json
{
  "doctor_verdict": "pass",
  "graph_status": "active",
  "corpus_status": "active",
  "profile_count": 1,
  "inspect_route": "fact",
  "selected_profile_count": 1,
  "suppressed_count": 0,
  "packet_sections": [
    "Brainstack Evidence Priority",
    "Brainstack Profile Match"
  ],
  "packet_preview_contains_requirement": true
}
```

## Gate Verdict

PASS for Phase 65 scope.

The kernel can now explain requested vs active capabilities and a concrete query path without mutating retrieval telemetry. This does not claim improved recall quality; Phase 66 owns that proof.
