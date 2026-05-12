#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.canonical_memory_event import validate_canonical_memory_event  # noqa: E402
from scripts.verify_current_truth_view import FIXED_REBUILT_AT, _baseline_events  # noqa: E402


def build_report() -> dict:
    with tempfile.TemporaryDirectory(prefix="brainstack-current-truth-l0-") as tmp:
        store = BrainstackStore(str(Path(tmp) / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        try:
            skipped_invalid = 0
            for event in _baseline_events():
                if validate_canonical_memory_event(event):
                    skipped_invalid += 1
                    continue
                store.record_canonical_memory_event(event)
            parity = store.compare_current_truth_l0_to_rebuild(limit=100, checked_at=FIXED_REBUILT_AT)
            snapshot = store.get_current_truth_l0_snapshot(limit=100, checked_at=FIXED_REBUILT_AT)
            failure_reasons: list[str] = []
            if parity["status"] != "pass":
                failure_reasons.append("l0_rebuild_parity_failed")
            if snapshot["rebuild"]["ordinary_hot_path_rebuild"] is not False:
                failure_reasons.append("ordinary_hot_path_rebuild_not_disabled")
            if snapshot["contract"]["second_write_authority"] is not False:
                failure_reasons.append("second_truth_authority")
            if snapshot["public_safety"]["public_safe"] is not True:
                failure_reasons.append("public_safety_not_pass")
            return {
                "schema": "brainstack.current_truth_l0_snapshot_verifier.v1",
                "status": "pass" if not failure_reasons else "fail",
                "failure_reasons": failure_reasons,
                "parity": parity,
                "summary": {
                    "skipped_invalid_canonical_fixture_count": skipped_invalid,
                    "current_truth_row_count": len(snapshot.get("current_truth_rows") or []),
                    "non_answerable_row_count": len(snapshot.get("non_answerable_rows") or []),
                    "ordinary_hot_path_rebuild": snapshot["rebuild"]["ordinary_hot_path_rebuild"],
                    "public_safe": snapshot["public_safety"]["public_safe"],
                },
            }
        finally:
            store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Brainstack current-truth L0 snapshot parity and hot-path boundary.")
    parser.add_argument("--out", type=Path, required=True, help="Path to write the public-safe JSON report.")
    args = parser.parse_args()
    report = build_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
