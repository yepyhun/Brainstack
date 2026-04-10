#!/usr/bin/env python3
"""Root entrypoint for Brainstack updater."""

from pathlib import Path
import runpy
import sys


SCRIPT = Path(__file__).resolve().parent / "scripts" / "update_hermes_with_brainstack.py"

if __name__ == "__main__":
    sys.path.insert(0, str(SCRIPT.parent))
    runpy.run_path(str(SCRIPT), run_name="__main__")
