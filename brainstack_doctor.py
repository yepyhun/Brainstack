#!/usr/bin/env python3
"""Root entrypoint for Brainstack doctor."""

from pathlib import Path
import runpy
import sys


SCRIPT = Path(__file__).resolve().parent / "scripts" / "brainstack_doctor.py"

if __name__ == "__main__":
    sys.path.insert(0, str(SCRIPT.parent))
    runpy.run_path(str(SCRIPT), run_name="__main__")
