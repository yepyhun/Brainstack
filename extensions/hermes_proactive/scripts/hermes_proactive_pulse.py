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


def _load_runtime_config(hermes_home: Path) -> dict[str, object]:
    path = hermes_home / "config.yaml"
    if not path.exists():
        return {"mode": "dry_run", "kill_switch": False}
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"mode": "dry_run", "kill_switch": False}
    if not isinstance(data, dict):
        return {"mode": "dry_run", "kill_switch": False}
    kernel_memory = data.get("kernel_memory") if isinstance(data.get("kernel_memory"), dict) else {}
    plugins = data.get("plugins") if isinstance(data.get("plugins"), dict) else {}
    brainstack = plugins.get("brainstack") if isinstance(plugins.get("brainstack"), dict) else {}
    mode = data.get("proactive_mode") or kernel_memory.get("proactive_mode") or brainstack.get("proactive_mode") or "dry_run"
    kill_switch = data.get("proactive_kill_switch")
    if kill_switch is None:
        kill_switch = kernel_memory.get("proactive_kill_switch")
    if kill_switch is None:
        kill_switch = brainstack.get("proactive_kill_switch")
    return {"mode": str(mode or "dry_run"), "kill_switch": bool(kill_switch)}


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
    output = produce_pulse(
        hermes_home=args.hermes_home,
        principal_scope_key=args.principal_scope_key,
        workspace_scope_key=args.workspace_scope_key,
        workstream_scope_key=args.workstream_scope_key,
        evolver_health_file=args.evolver_health_file,
        stale_inbox_threshold=args.stale_inbox_threshold,
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
    print(json.dumps(output, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
