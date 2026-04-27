#!/usr/bin/env python3
"""Write Phase 189 product matrix artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ga_product_matrix import (  # noqa: E402
    discord_interaction_matrix,
    memory_correctness_matrix,
    product_e2e_matrix,
    provider_latency_resilience_matrix,
    security_privacy_approval_report,
    tool_capability_safety_matrix,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    write_json(out / "189-PRODUCT-E2E-MATRIX.json", product_e2e_matrix())
    write_json(out / "189-MEMORY-CORRECTNESS-MATRIX.json", memory_correctness_matrix())
    write_json(out / "189-TOOL-CAPABILITY-SAFETY.json", tool_capability_safety_matrix())
    write_json(out / "189-PROVIDER-LATENCY-RESILIENCE.json", provider_latency_resilience_matrix())
    write_json(out / "189-DISCORD-INTERACTION-MATRIX.json", discord_interaction_matrix())
    security_payload, security_md = security_privacy_approval_report()
    write_json(out / "189-SECURITY-PRIVACY-APPROVAL.json", security_payload)
    (out / "189-SECURITY-PRIVACY-APPROVAL.md").write_text(security_md, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
