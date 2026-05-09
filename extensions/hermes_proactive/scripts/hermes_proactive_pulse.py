#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERMES_ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
plugin_path = HERMES_ROOT / "plugins" / "memory"
if plugin_path.exists() and str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))
if (HERMES_ROOT / "brainstack").exists() and str(HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(HERMES_ROOT))

from hermes_proactive.pulse_producer import produce_pulse, project_pulse_output  # noqa: E402
from hermes_proactive.workrun import checkpoint_workrun, finish_workrun, prune_completed_workruns, start_workrun  # noqa: E402
from hermes_proactive.config import load_runtime_config  # noqa: E402


def _load_runtime_config(hermes_home: Path) -> dict[str, object]:
    return load_runtime_config(hermes_home)


def _delivery_allowed(hermes_home: Path, requested: bool) -> bool:
    config = _load_runtime_config(hermes_home)
    return bool(requested) and config["mode"] == "live" and not bool(config["kill_switch"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes proactive PulseProducer.")
    parser.add_argument("command", choices=("dry-run", "trigger"))
    parser.add_argument("--hermes-home", required=True, type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--principal-scope-key", default="runtime:brainstack")
    parser.add_argument("--workspace-scope-key", default="workspace:default")
    parser.add_argument("--workstream-scope-key", default="")
    parser.add_argument("--evolver-health-file", type=Path)
    parser.add_argument("--stale-inbox-threshold", type=int, default=1)
    parser.add_argument("--create-outbox", action="store_true")
    args = parser.parse_args()
    workrun = start_workrun(
        hermes_home=args.hermes_home,
        source_kind="proactive_pulse",
        source_id="brainstack_proactive_pulse",
        objective="Inspect proactive runtime signals and surface safe recovery candidates.",
        recovery_policy="rerun pulse and inspect recovery candidates before retrying side-effect work",
        side_effect_risk="none",
        next_safe_action="rerun proactive pulse in dry-run or inspect listed recovery candidates",
        metadata={"command": args.command},
    )
    try:
        output = produce_pulse(
            hermes_home=args.hermes_home,
            principal_scope_key=args.principal_scope_key,
            workspace_scope_key=args.workspace_scope_key,
            workstream_scope_key=args.workstream_scope_key,
            evolver_health_file=args.evolver_health_file,
            stale_inbox_threshold=args.stale_inbox_threshold,
        )
        checkpoint_workrun(
            hermes_home=args.hermes_home,
            run_id=str(workrun["run_id"]),
            checkpoint_ref=str(output.get("run_id") or "pulse_output"),
            next_safe_action="project pulse output only if delivery policy allows it",
        )
        if args.command == "trigger" and args.db is not None:
            output = {
                **output,
                "projection": project_pulse_output(
                    db_path=args.db,
                    output=output,
                    create_outbox=_delivery_allowed(args.hermes_home, args.create_outbox),
                ),
            }
        finish_workrun(
            hermes_home=args.hermes_home,
            run_id=str(workrun["run_id"]),
            status="completed",
            output_ref=str(output.get("run_id") or ""),
            next_safe_action="none",
        )
        prune_completed_workruns(hermes_home=args.hermes_home, keep_completed=200)
        print(json.dumps(output, ensure_ascii=True, indent=2, sort_keys=True))
        return 0
    except BaseException as exc:
        finish_workrun(
            hermes_home=args.hermes_home,
            run_id=str(workrun["run_id"]),
            status="interrupted",
            error_summary=str(exc),
            next_safe_action="inspect the last checkpoint and rerun pulse if safe",
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
