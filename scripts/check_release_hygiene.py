#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_release_hygiene_checker():
    installer_path = REPO_ROOT / "scripts" / "install_into_hermes.py"
    spec = importlib.util.spec_from_file_location("brainstack_installer_for_hygiene", installer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load installer module from {installer_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module._check_release_hygiene


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Brainstack release payload hygiene.")
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help="Repository root to inspect")
    parser.add_argument("--json", action="store_true", help="Print the full machine-readable report")
    args = parser.parse_args()

    report = _load_release_hygiene_checker()(args.repo.expanduser().resolve())
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif report["status"] == "pass":
        print("PASS release hygiene: no tracked/staged private runtime paths or high-confidence secrets")
    else:
        print("FAIL release hygiene", file=sys.stderr)
        for key in ("private_tracked", "private_staged", "secret_like_tracked"):
            values = report.get(key) or []
            if values:
                print(f"{key}: {', '.join(values[:12])}", file=sys.stderr)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
