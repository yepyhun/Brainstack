#!/usr/bin/env python3
"""Convert failed product probes into repair bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.product_contracts import ProductProbeEnvelope, build_failure_bundles, dump_json  # noqa: E402


def triage(input_path: Path) -> dict[str, object]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    probes = [ProductProbeEnvelope.from_dict(item) for item in payload.get("probes", [])]
    return {
        "schema": "brainstack.failure_triage.v1",
        "source": str(input_path),
        "failure_bundles": build_failure_bundles(probes),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    payload = triage(Path(args.input))
    dump_json(Path(args.out), payload)
    print(f"WROTE {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

