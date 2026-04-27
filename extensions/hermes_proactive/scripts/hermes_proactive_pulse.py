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

from hermes_proactive.pulse_producer import produce_pulse, project_pulse_output  # noqa: E402


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
    output = produce_pulse(
        hermes_home=args.hermes_home,
        principal_scope_key=args.principal_scope_key,
        workspace_scope_key=args.workspace_scope_key,
        workstream_scope_key=args.workstream_scope_key,
        evolver_health_file=args.evolver_health_file,
        stale_inbox_threshold=args.stale_inbox_threshold,
    )
    if args.command == "trigger" and args.db is not None:
        output = {**output, "projection": project_pulse_output(db_path=args.db, output=output, create_outbox=args.create_outbox)}
    print(json.dumps(output, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
