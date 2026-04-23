#!/usr/bin/env python3
"""Print the Brainstack host-patch surface in JSON or Markdown."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = REPO_ROOT / "scripts" / "install_into_hermes.py"


def _load_installer_module():
    spec = importlib.util.spec_from_file_location("brainstack_installer", INSTALLER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load installer module from {INSTALLER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _to_markdown(rows: list[dict[str, Any]], runtime: str) -> str:
    lines = [
        f"# Brainstack Host Patch Inventory ({runtime})",
        "",
        "This report is generated from `scripts/install_into_hermes.py`.",
        "",
        "| Target | Patcher | Scope | Purpose | Why |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        purpose = str(row.get("purpose", "")).replace("|", "\\|")
        why = str(row.get("why", "")).replace("|", "\\|")
        lines.append(
            f"| `{row['target']}` | `{row['patcher']}` | `{row['scope']}` | {purpose} | {why} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=("source", "docker"), default="source")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()

    installer = _load_installer_module()
    rows = installer._selected_host_patch_inventory(args.runtime)
    if args.format == "json":
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        print(_to_markdown(rows, args.runtime), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
