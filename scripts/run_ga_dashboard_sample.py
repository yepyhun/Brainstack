#!/usr/bin/env python3
"""Write sample GA readiness dashboard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.product_contracts import ProductProbeEnvelope, ProbeOwner, ProbeStatus, Repairability, Severity  # noqa: E402
from scripts.ga_dashboard import build_ga_dashboard  # noqa: E402


def sample_probes() -> list[ProductProbeEnvelope]:
    return [
        ProductProbeEnvelope(
            probe_id="ga.source_wizard_docker",
            phase="187",
            scenario_id="source_wizard_docker_parity",
            status=ProbeStatus.PASS,
            owner=ProbeOwner.SOURCE_OF_TRUTH_PARITY,
            repairability=Repairability.NONE,
            severity=Severity.P0,
            reason_code="SOURCE_WIZARD_DOCKER_PARITY_PASS",
        ),
        ProductProbeEnvelope(
            probe_id="ga.synthetic_gateway",
            phase="187",
            scenario_id="synthetic_gateway_e2e",
            status=ProbeStatus.PASS,
            owner=ProbeOwner.SOURCE_OF_TRUTH_PARITY,
            repairability=Repairability.NONE,
            severity=Severity.P1,
            reason_code="SYNTHETIC_GATEWAY_E2E_PASS",
            observed={
                "path_proof_required": True,
                "path_proof": {
                    "used_gateway_runner": True,
                    "used_prompt_builder": True,
                    "used_brainstack_packet": True,
                    "used_final_validator": True,
                },
            },
        ),
        ProductProbeEnvelope(
            probe_id="ga.live_gate",
            phase="187",
            scenario_id="live_gate",
            status=ProbeStatus.BLOCKED,
            owner=ProbeOwner.DOCKER_RUNTIME_CONFIG,
            repairability=Repairability.HUMAN_DECISION_REQUIRED,
            severity=Severity.P1,
            reason_code="LIVE_GATE_NOT_RUN",
            recommended_playbook="LIVE_GATE_EXECUTION_REQUIRED",
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    dashboard = build_ga_dashboard(sample_probes())
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dashboard, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
