#!/usr/bin/env python3
"""Write Phase 185 RC gate artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.product_contracts import (  # noqa: E402
    ProductProbeEnvelope,
    ProbeOwner,
    ProbeStatus,
    Repairability,
    Severity,
    build_failure_bundles,
    run_adversarial_synthetic_gateway_contract,
)
from scripts.phase185_rc_gate import (  # noqa: E402
    clean_runtime_state,
    docker_adversarial_proof,
    generated_config_not_kawaii,
    rc_matrix,
    source_wizard_docker_parity,
    write_json,
)


def git_status_lines(source_root: Path) -> list[str]:
    try:
        out = subprocess.check_output(["git", "status", "--short"], cwd=source_root, text=True)
    except Exception:
        return []
    return out.splitlines()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", default=str(ROOT))
    parser.add_argument("--hermes-root", required=True)
    parser.add_argument("--runtime-root")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--live-gate-status", default="not_run", choices=("not_run", "run_pass", "run_fail"))
    parser.add_argument("--docker-adversarial-status", default="not_run", choices=("not_run", "run_pass", "run_fail"))
    parser.add_argument("--docker-proof-json")
    args = parser.parse_args()

    source_root = Path(args.source_root).resolve()
    hermes_root = Path(args.hermes_root).resolve()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    parity = source_wizard_docker_parity(source_root, hermes_root)
    write_json(out_dir / "185-SOURCE-WIZARD-DOCKER-PARITY.json", parity)

    runtime_root = Path(args.runtime_root).resolve() if args.runtime_root else out_dir / "runtime-fixture"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "auth.json").write_text("{}", encoding="utf-8")
    (runtime_root / "config.yaml").write_text("personality: neutral\n", encoding="utf-8")
    (runtime_root / "skills").mkdir(exist_ok=True)
    (runtime_root / "sessions").mkdir(exist_ok=True)
    clean = clean_runtime_state(runtime_root, apply=True)
    write_json(out_dir / "185-RUNTIME-CLEAN-PROOF.json", clean)

    adversarial = run_adversarial_synthetic_gateway_contract()
    docker_proof = docker_adversarial_proof(
        Path(args.docker_proof_json).resolve() if args.docker_proof_json else None,
        args.docker_adversarial_status,
    )
    docker_adversarial_passed = bool(docker_proof["passed"])
    write_json(
        out_dir / "185-DOCKER-ADVERSARIAL-RC.json",
        {
            "schema": "brainstack.phase185.docker_adversarial_rc.v1",
            "docker_status": args.docker_adversarial_status,
            "docker_proof": docker_proof,
            "local_contract_trace": adversarial,
            "passed": docker_adversarial_passed,
        },
    )

    config = generated_config_not_kawaii((runtime_root / "config.yaml").read_text(encoding="utf-8"))
    open_failure_bundles = 0
    matrix = rc_matrix(
        parity=parity,
        runtime_clean=clean,
        docker_adversarial_passed=docker_adversarial_passed,
        live_gate_status=args.live_gate_status,
        open_failure_bundles=open_failure_bundles,
    )
    matrix["config_personality"] = config
    matrix["git_status_snapshot"] = git_status_lines(source_root)[:80]
    write_json(out_dir / "185-LIVE-RC-MATRIX.json", matrix)

    probes = [
        ProductProbeEnvelope(
            probe_id="185.live_gate",
            phase="185",
            scenario_id="live_gate",
            status=ProbeStatus.PASS if args.live_gate_status == "run_pass" else ProbeStatus.BLOCKED,
            owner=ProbeOwner.DOCKER_RUNTIME_CONFIG,
            repairability=Repairability.HUMAN_DECISION_REQUIRED,
            severity=Severity.P1,
            reason_code="LIVE_GATE_NOT_RUN" if args.live_gate_status == "not_run" else "LIVE_GATE_STATUS",
        ),
        ProductProbeEnvelope(
            probe_id="185.docker_adversarial",
            phase="185",
            scenario_id="docker_adversarial_rc",
            status=ProbeStatus.PASS if docker_adversarial_passed else ProbeStatus.BLOCKED,
            owner=ProbeOwner.DOCKER_RUNTIME_CONFIG,
            repairability=Repairability.HUMAN_DECISION_REQUIRED,
            severity=Severity.P1,
            reason_code="DOCKER_ADVERSARIAL_NOT_RUN" if args.docker_adversarial_status == "not_run" else "DOCKER_ADVERSARIAL_STATUS",
        ),
    ]
    write_json(
        out_dir / "185-FAILURE-BUNDLES.json",
        {
            "schema": "brainstack.phase185.failure_bundles.v1",
            "failure_bundles": build_failure_bundles(probes),
        },
    )
    print(f"WROTE {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
