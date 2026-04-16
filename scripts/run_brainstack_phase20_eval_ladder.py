#!/usr/bin/env python3
"""Run the bounded Phase 20 proof ladder without forcing a live rebuild."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _env_path(*names: str) -> Path | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return Path(value).expanduser()
    return None


DEFAULT_HERMES_ROOT = _env_path("BRAINSTACK_HERMES_ROOT", "HERMES_ROOT")
DEFAULT_PYTHON = Path(os.environ.get("BRAINSTACK_PYTHON") or sys.executable).expanduser()
DEFAULT_BENCH_REPORT = REPO_ROOT / "reports" / "phase20" / "brainstack-final-boss.json"


def _build_overlay() -> tempfile.TemporaryDirectory[str]:
    tmp_dir = tempfile.TemporaryDirectory(prefix="brainstack-phase20-eval-")
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
    parser = argparse.ArgumentParser(description="Run the bounded Brainstack Phase 20 proof ladder.")
    parser.add_argument(
        "--gate",
        choices=["a", "b", "c", "d", "e", "all"],
        default="all",
        help="Which gate to run. 'all' runs A through E.",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=DEFAULT_PYTHON,
        help="Python interpreter used for pytest and helper scripts.",
    )
    parser.add_argument(
        "--hermes-root",
        type=Path,
        default=DEFAULT_HERMES_ROOT,
        help="Hermes checkout used for plugin import seams and benchmark runs.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=15,
        help="Sample size for the final-boss Brainstack LongMemEval subset.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_BENCH_REPORT,
        help="Where to write the final-boss benchmark report.",
    )
    args = parser.parse_args()

    if args.hermes_root is None:
        raise SystemExit("--hermes-root is required (or set BRAINSTACK_HERMES_ROOT / HERMES_ROOT).")

    python_bin = args.python
    hermes_root = args.hermes_root
    overlay = _build_overlay()
    overlay_root = Path(overlay.name)
    env = _env(overlay_root=overlay_root, hermes_root=hermes_root)
    args.report_path.parent.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    statuses: dict[str, str] = {}
    try:
        if args.gate in {"a", "all"}:
            rc = _run(
                "Gate A: attributable proof streams and cross-store coherence",
                [
                    str(python_bin),
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_brainstack_phase20_proof.py",
                ],
                env,
            )
            statuses["gate_a"] = "passed" if rc == 0 else "failed"
            if rc:
                failures.append("Gate A")

        if args.gate in {"b", "all"}:
            gate_b_cmds = [
                [
                    str(python_bin),
                    "scripts/run_brainstack_phase17_eval_ladder.py",
                    "--gate",
                    "a",
                ],
                [
                    str(python_bin),
                    "scripts/run_brainstack_phase17_eval_ladder.py",
                    "--gate",
                    "b",
                ],
                [
                    str(python_bin),
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_brainstack_graph_backend_kuzu.py",
                    "tests/test_brainstack_real_world_flows.py",
                    "-k",
                    "temporal_graph_truth_shows_current_and_prior_state or non_temporal_graph_query_prefers_current_truth_without_history_spam",
                ],
                [
                    str(python_bin),
                    "scripts/run_brainstack_phase19_eval_ladder.py",
                    "--gate",
                    "a",
                ],
                [
                    str(python_bin),
                    "scripts/run_brainstack_phase19_eval_ladder.py",
                    "--gate",
                    "b",
                ],
            ]
            rc = 0
            for index, cmd in enumerate(gate_b_cmds, start=1):
                step_rc = _run(f"Gate B.{index}: restored-layer regression", cmd, env)
                if step_rc and rc == 0:
                    rc = step_rc
            statuses["gate_b"] = "passed" if rc == 0 else "failed"
            if rc:
                failures.append("Gate B")

        if args.gate in {"c", "all"}:
            rc = _run(
                "Gate C: integrated conversational proof flows",
                [
                    str(python_bin),
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_brainstack_real_world_flows.py",
                    "-k",
                    (
                        "cross_session_prefetch_recalls_preference_and_shared_work or "
                        "same_session_prefetch_surfaces_fresh_style_preferences_through_recent_continuity or "
                        "temporal_graph_truth_shows_current_and_prior_state or "
                        "corpus_recall_returns_relevant_bounded_document_sections"
                    ),
                ],
                env,
            )
            statuses["gate_c"] = "passed" if rc == 0 else "failed"
            if rc:
                failures.append("Gate C")

        if args.gate in {"d", "all"}:
            rc = _run(
                "Gate D: cross-store resilience and degraded-read proof",
                [
                    str(python_bin),
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_brainstack_phase20_proof.py",
                    "-k",
                    "cross_store",
                ],
                env,
            )
            statuses["gate_d"] = "passed" if rc == 0 else "failed"
            if rc:
                failures.append("Gate D")

        if args.gate in {"e", "all"}:
            api_key_present = bool(os.environ.get("COMET_API_KEY") or os.environ.get("COMETAPI_API_KEY"))
            if not api_key_present:
                print("\n== Gate E: skipped ==")
                print("COMET_API_KEY or COMETAPI_API_KEY is missing, so the final-boss Brainstack benchmark was not run.")
                statuses["gate_e"] = "skipped_missing_api_key"
            else:
                rc = _run(
                    "Gate E: final-boss Brainstack LongMemEval subset",
                    [
                        str(python_bin),
                        "scripts/run_brainstack_longmemeval_subset.py",
                        "--sample-size",
                        str(args.sample_size),
                        "--report-path",
                        str(args.report_path),
                    ],
                    env,
                )
                statuses["gate_e"] = "passed" if rc == 0 else "failed"
                if rc:
                    failures.append("Gate E")
    finally:
        overlay.cleanup()

    print("\nPhase 20 gate status:")
    print(json.dumps(statuses, indent=2, sort_keys=True))

    if failures:
        print("\nPhase 20 eval ladder failed:", ", ".join(failures))
        return 1

    print("\nPhase 20 eval ladder passed for requested gates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
