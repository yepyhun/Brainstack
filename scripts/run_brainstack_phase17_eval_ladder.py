#!/usr/bin/env python3
"""Run the bounded Phase 17 L1 eval ladder without requiring a live rebuild."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HERMES_ROOT = Path("/home/lauratom/Asztal/ai/memory-repo-bakeoff/hermes-agent-bestie-latest")
DEFAULT_PYTHON = Path("/home/lauratom/Asztal/ai/hermes-agent-port/venv/bin/python")


def _build_overlay() -> tempfile.TemporaryDirectory[str]:
    tmp_dir = tempfile.TemporaryDirectory(prefix="brainstack-phase17-eval-")
    root = Path(tmp_dir.name)
    plugins_dir = root / "plugins"
    memory_dir = plugins_dir / "memory"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    memory_dir.mkdir(parents=True, exist_ok=True)
    (plugins_dir / "__init__.py").write_text("", encoding="utf-8")
    (memory_dir / "__init__.py").write_text("", encoding="utf-8")
    target = memory_dir / "brainstack"
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(REPO_ROOT / "brainstack", target_is_directory=True)
    return tmp_dir


def _env(*, overlay_root: Path, hermes_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(overlay_root), str(hermes_root)]
    existing = env.get("PYTHONPATH", "").strip()
    if existing:
        pythonpath_parts.append(existing)
    env["PYTHONPATH"] = ":".join(pythonpath_parts)
    return env


def _run(label: str, cmd: list[str], env: dict[str, str]) -> int:
    print(f"\n== {label} ==")
    print(" ".join(cmd))
    completed = subprocess.run(cmd, cwd=REPO_ROOT, env=env)
    return int(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bounded Brainstack Phase 17 eval ladder.")
    parser.add_argument(
        "--gate",
        choices=["a", "b", "c", "all"],
        default="all",
        help="Which gate to run. 'all' runs A then B and C if credentials exist.",
    )
    parser.add_argument(
        "--python",
        default=str(DEFAULT_PYTHON),
        help="Python interpreter used for pytest and helper scripts.",
    )
    parser.add_argument(
        "--hermes-root",
        default=str(DEFAULT_HERMES_ROOT),
        help="Hermes checkout used for plugin import seams and benchmark runs.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=3,
        help="Sample size for Gate C LongMemEval subset.",
    )
    args = parser.parse_args()

    python_bin = Path(args.python)
    hermes_root = Path(args.hermes_root)
    overlay = _build_overlay()
    overlay_root = Path(overlay.name)
    env = _env(overlay_root=overlay_root, hermes_root=hermes_root)

    failures: list[str] = []

    try:
        if args.gate in {"a", "all"}:
            rc = _run(
                "Gate A: bounded acceptance",
                [
                    str(python_bin),
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_brainstack_executive_retrieval.py",
                    "tests/test_brainstack_retrieval_contract.py",
                ],
                env,
            )
            if rc:
                failures.append("Gate A")

        if args.gate in {"b", "all"}:
            rc = _run(
                "Gate B: smartening-oriented flows",
                [
                    str(python_bin),
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_brainstack_real_world_flows.py",
                    "tests/test_brainstack_usefulness.py",
                ],
                env,
            )
            if rc:
                failures.append("Gate B")

        if args.gate in {"c", "all"}:
            api_key_present = bool(os.environ.get("COMET_API_KEY") or os.environ.get("COMETAPI_API_KEY"))
            if not api_key_present:
                print("\n== Gate C: skipped ==")
                print("COMET_API_KEY or COMETAPI_API_KEY is missing, so the Brainstack LongMemEval subset was not run.")
            else:
                rc = _run(
                    "Gate C: small Brainstack LongMemEval subset",
                    [
                        str(python_bin),
                        "scripts/run_brainstack_longmemeval_subset.py",
                        "--sample-size",
                        str(args.sample_size),
                    ],
                    env,
                )
                if rc:
                    failures.append("Gate C")
    finally:
        overlay.cleanup()

    if failures:
        print("\nPhase 17 eval ladder failed:", ", ".join(failures))
        return 1

    print("\nPhase 17 eval ladder passed for requested gates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
