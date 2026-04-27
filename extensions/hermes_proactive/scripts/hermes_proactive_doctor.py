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

from hermes_proactive.doctor import proactive_extension_doctor  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes proactive extension doctor.")
    parser.add_argument("--hermes-home", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(proactive_extension_doctor(hermes_home=args.hermes_home), ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
