#!/usr/bin/env python3
"""Build a deterministic native-vs-Brainstack baseline attribution matrix."""

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
    build_capability_manifest,
    dump_json,
)


def _hash_config(path: Path) -> str:
    config = path / "config.yaml"
    if not config.exists():
        config = path / "hermes-config" / "bestie" / "config.yaml"
    if not config.exists():
        return "missing"
    import hashlib

    return hashlib.sha256(config.read_bytes()).hexdigest()[:24]


def _markers(path: Path) -> dict[str, bool]:
    return {
        "exists": path.exists(),
        "run_agent": (path / "run_agent.py").exists(),
        "toolloader": (path / "hermes_deferred_tools.py").exists(),
        "gateway": (path / "gateway").exists(),
        "brainstack_plugin": (path / "brainstack").exists() or (path / "plugins" / "brainstack").exists(),
    }


def build_matrix(native: Path, brainstack: Path) -> dict[str, object]:
    native_markers = _markers(native)
    brainstack_markers = _markers(brainstack)
    manifest = build_capability_manifest(
        configured_capabilities=("filesystem.search_read", "terminal.execute", "web.browse"),
        executable_capabilities=("filesystem.search_read", "terminal.execute"),
        loaded_schema_capabilities=("memory.recall",),
        approval_required_capabilities=("terminal.execute",),
        unavailable_reasons={"web.browse": "missing_backend_or_env_key"},
    )

    probes = [
        ProductProbeEnvelope(
            probe_id="173-native-boot",
            phase="173",
            scenario_id="baseline_native_hermes_boot",
            status=ProbeStatus.PASS if native_markers["exists"] else ProbeStatus.INVALID_FIXTURE,
            owner=ProbeOwner.TEST_FIXTURE_INVALID if not native_markers["exists"] else ProbeOwner.NATIVE_HERMES_OR_MODEL,
            repairability=Repairability.INVALID_TEST_FIXTURE if not native_markers["exists"] else Repairability.NONE,
            severity=Severity.P1,
            reason_code="NATIVE_PATH_PRESENT" if native_markers["exists"] else "NATIVE_PATH_MISSING",
            observed=native_markers,
            expected={"exists": True},
        ),
        ProductProbeEnvelope(
            probe_id="173-brainstack-boot",
            phase="173",
            scenario_id="baseline_brainstack_install_boot",
            status=ProbeStatus.PASS if brainstack_markers["exists"] else ProbeStatus.INVALID_FIXTURE,
            owner=ProbeOwner.TEST_FIXTURE_INVALID if not brainstack_markers["exists"] else ProbeOwner.BRAINSTACK_INSTALLER_OR_WIZARD,
            repairability=Repairability.INVALID_TEST_FIXTURE if not brainstack_markers["exists"] else Repairability.NONE,
            severity=Severity.P1,
            reason_code="BRAINSTACK_PATH_PRESENT" if brainstack_markers["exists"] else "BRAINSTACK_PATH_MISSING",
            observed=brainstack_markers,
            expected={"exists": True},
        ),
        ProductProbeEnvelope(
            probe_id="173-capability-manifest",
            phase="173",
            scenario_id="capability_manifest_diff",
            status=ProbeStatus.PASS,
            owner=ProbeOwner.HERMES_CAPABILITY_MANIFEST,
            repairability=Repairability.NONE,
            severity=Severity.P1,
            reason_code="CAPABILITY_STATUS_TYPED",
            observed=manifest,
            expected={"statuses": ["configured_available", "configured_unavailable", "not_configured", "disabled_by_admin"]},
        ),
    ]
    return {
        "schema": "brainstack.baseline_matrix.v1",
        "config_parity": {
            "native_config_hash": _hash_config(native),
            "brainstack_config_hash": _hash_config(brainstack),
        },
        "probes": [probe.to_dict() for probe in probes],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", required=True)
    parser.add_argument("--brainstack", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    payload = build_matrix(Path(args.native), Path(args.brainstack))
    dump_json(Path(args.out), payload)
    print(f"WROTE {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
