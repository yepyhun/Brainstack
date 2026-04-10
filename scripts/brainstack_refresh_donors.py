#!/usr/bin/env python3
"""Bounded donor refresh reporter for Brainstack.

This script does not pull or merge upstream donor projects. It reports the
tracked donor baselines, verifies the local adapter seams exist, and can run the
declared compatibility smoke tests so refresh work stays honest instead of
pretending to be fully automatic.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List
import shutil

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_registry_module():
    module_path = REPO_ROOT / "brainstack" / "donors" / "registry.py"
    spec = importlib.util.spec_from_file_location("brainstack_registry_runtime", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load donor registry from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


list_donor_specs = _load_registry_module().list_donor_specs


def _validate_selected(selected: set[str] | None, available: set[str]) -> None:
    if not selected:
        return
    unknown = sorted(selected - available)
    if unknown:
        raise ValueError(f"Unknown donor key(s): {', '.join(unknown)}")


def _resolve_adapter_path(local_adapter: str) -> Path:
    candidate = (REPO_ROOT / local_adapter).resolve()
    try:
        candidate.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError(f"Adapter path escapes repo root: {local_adapter}") from exc
    return candidate


def _run_smoke(smoke_target: str) -> Dict[str, Any]:
    if shutil.which("uv"):
        command = ["uv", "run", "--extra", "dev", "python", "-m", "pytest", *shlex.split(smoke_target), "-q"]
    else:
        command = [sys.executable, "-m", "pytest", *shlex.split(smoke_target), "-q"]
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
    return {
        "target": smoke_target,
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": result.returncode,
        "stdout_tail": result.stdout.strip().splitlines()[-5:],
        "stderr_tail": result.stderr.strip().splitlines()[-5:],
        "verdict": "pass" if result.returncode == 0 else "fail",
    }


def _build_report(selected: set[str] | None, run_smoke: bool) -> Dict[str, Any]:
    specs = list_donor_specs()
    available = {spec.key for spec in specs}
    _validate_selected(selected, available)
    donors: List[Dict[str, Any]] = []
    for spec in specs:
        if selected and spec.key not in selected:
            continue
        adapter_path = _resolve_adapter_path(spec.local_adapter)
        smoke_results = [_run_smoke(target) for target in spec.smoke_tests] if run_smoke else []
        donors.append(
            {
                "key": spec.key,
                "role": spec.role,
                "strategy": spec.strategy,
                "upstream": spec.upstream,
                "baseline": spec.baseline,
                "local_owner": spec.local_owner,
                "local_adapter": spec.local_adapter,
                "local_adapter_exists": adapter_path.exists(),
                "notes": spec.notes,
                "smoke_tests": list(spec.smoke_tests),
                "smoke_results": smoke_results,
                "smoke_verdict": (
                    "not-run"
                    if not run_smoke
                    else ("pass" if all(item["verdict"] == "pass" for item in smoke_results) else "fail")
                ),
                "refresh_model": "manual donor review plus local adapter refresh",
            }
        )
    return {
        "mode": "bounded-refresh-report",
        "repo_root": str(REPO_ROOT),
        "selected_donors": sorted(selected) if selected else "all",
        "donor_count": len(donors),
        "run_smoke": run_smoke,
        "donors": donors,
        "honesty_note": (
            "This report verifies local adapter seams and optional local smoke tests only. "
            "It does not claim upstream code was auto-merged or that compatibility is guaranteed without review."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report Brainstack donor baselines and optional smoke verdicts.")
    parser.add_argument("--donor", action="append", help="Restrict the report to one donor key. Can be repeated.")
    parser.add_argument("--run-smoke", action="store_true", help="Run the registered local pytest smoke tests.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when an adapter is missing or smoke fails.")
    parser.add_argument("--format", choices=("json", "text"), default="text", help="Output format.")
    args = parser.parse_args()

    selected = set(args.donor or [])
    try:
        report = _build_report(selected=selected or None, run_smoke=args.run_smoke)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("Brainstack donor refresh report")
        print(f"repo_root: {report['repo_root']}")
        print(f"selected_donors: {report['selected_donors']}")
        print(f"run_smoke: {report['run_smoke']}")
        print("")
        for donor in report["donors"]:
            print(f"[{donor['key']}] {donor['role']}")
            print(f"  strategy: {donor['strategy']}")
            print(f"  upstream: {donor['upstream']}")
            print(f"  baseline: {donor['baseline']}")
            print(f"  local_owner: {donor['local_owner']}")
            print(f"  local_adapter: {donor['local_adapter']} ({'ok' if donor['local_adapter_exists'] else 'missing'})")
            print(f"  smoke_verdict: {donor['smoke_verdict']}")
            if donor["smoke_results"]:
                for result in donor["smoke_results"]:
                    print(f"    - {result['target']}: {result['verdict']}")
            print("")
        print(report["honesty_note"])

    if args.strict:
        for donor in report["donors"]:
            if not donor["local_adapter_exists"]:
                return 1
            if args.run_smoke and donor["smoke_verdict"] != "pass":
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
