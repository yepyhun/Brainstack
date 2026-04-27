#!/usr/bin/env python3
"""Run Phase 184 adversarial synthetic Gateway-equivalent contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.product_contracts import (  # noqa: E402
    ProductProbeEnvelope,
    build_failure_bundles,
    dump_json,
    run_adversarial_synthetic_gateway_contract,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    result = run_adversarial_synthetic_gateway_contract()
    dump_json(out_dir / "184-ADVERSARIAL-E2E-TRACE.json", result)
    dump_json(out_dir / "184-PROMPT-PACKET-PROOF.json", result["packet"])
    dump_json(out_dir / "184-PHRASE-PROVENANCE-SAMPLE.json", result["phrase_provenance"])

    probes = [ProductProbeEnvelope.from_dict(item) for item in result["probes"]]
    sample = [dict(item) for item in result["probes"]]
    sample[0]["status"] = "fail"
    sample_bundles = build_failure_bundles(ProductProbeEnvelope.from_dict(item) for item in sample)
    dump_json(
        out_dir / "184-FAILURE-BUNDLE-SAMPLES.json",
        {
            "schema": "brainstack.phase184.failure_bundle_samples.v1",
            "open_failure_bundles": build_failure_bundles(probes),
            "sample_only_bundles": sample_bundles,
        },
    )
    print(f"WROTE {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
