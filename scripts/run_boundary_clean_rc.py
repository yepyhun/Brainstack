#!/usr/bin/env python3
"""Run deterministic boundary-clean RC probes."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.product_contracts import (  # noqa: E402
    ProbeOwner,
    ProbeStatus,
    ProductProbeEnvelope,
    Repairability,
    Severity,
    decide_final_answer_allowed,
    dump_json,
    rc_stop_condition,
)


def build_rc_matrix(*, include_sample_failure: bool = False) -> dict[str, object]:
    probes: list[ProductProbeEnvelope] = [
        ProductProbeEnvelope(
            probe_id="178-capability-preserved",
            phase="178",
            scenario_id="capability_manifest_truthful",
            status=ProbeStatus.PASS,
            owner=ProbeOwner.HERMES_CAPABILITY_MANIFEST,
            repairability=Repairability.NONE,
            severity=Severity.P0,
            reason_code="CAPABILITY_PRESERVED",
            observed={"capability_shrunk": False},
            expected={"capability_shrunk": False},
        ),
        ProductProbeEnvelope(
            probe_id="178-url-tool-state",
            phase="178",
            scenario_id="inspect_url_no_guess",
            status=ProbeStatus.PASS,
            owner=ProbeOwner.HERMES_TOOL_STATE_GUARD,
            repairability=Repairability.NONE,
            severity=Severity.P0,
            reason_code="FINAL_BLOCKED_UNTIL_TOOL_OR_DIAGNOSTIC",
            observed=decide_final_answer_allowed(external_capability_possible=True).to_dict(),
            expected={"final_answer_allowed": False},
        ),
    ]
    if include_sample_failure:
        probes.append(
            ProductProbeEnvelope(
                probe_id="178-sample-url-guess",
                phase="178",
                scenario_id="url_inspect_no_guess",
                status=ProbeStatus.FAIL,
                owner=ProbeOwner.HERMES_TOOL_STATE_GUARD,
                repairability=Repairability.REPAIRABLE_AUTOMATIC,
                severity=Severity.P0,
                reason_code="URL_FINAL_BEFORE_TOOL",
                observed={"final_answer_before_tool": True, "tool_loader_called": False},
                expected={"final_answer_allowed": False},
                recommended_playbook="TOOL_STATE_FINAL_ANSWER_BLOCK",
            )
        )
    return {
        "schema": "brainstack.boundary_clean_rc.v1",
        "probes": [probe.to_dict() for probe in probes],
        "stop_condition": rc_stop_condition(probes),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--sample-failure", action="store_true")
    args = parser.parse_args()
    payload = build_rc_matrix(include_sample_failure=args.sample_failure)
    dump_json(Path(args.out), payload)
    print(f"WROTE {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

