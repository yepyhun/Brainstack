#!/usr/bin/env python3
"""Write non-runtime Phase 179.5 proof artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.product_contracts import default_hot_containment_toggles, dump_json  # noqa: E402


def write_artifacts(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    dump_json(out_dir / "179.5-CONTAINMENT-TOGGLES.json", default_hot_containment_toggles().to_dict())
    (out_dir / "179.5-OWNER-CLASSIFICATION.md").write_text(
        "\n".join(
            [
                "# Phase 179.5 Owner Classification",
                "",
                "- `production_personality`: Hermes presentation.",
                "- `conversation/heavy capability gate`: Hermes runtime/capability manifest.",
                "- `direct renderer negative/generic path`: Hermes presentation/runtime renderer.",
                "- `assistant-output model-facing continuity`: Brainstack retrieval/packet visibility until Phase 180 firewall.",
                "- `ToolLoader fallback`: Hermes ToolLoader/runtime.",
                "- `source/wizard parity`: Brainstack installer/wizard source-of-truth.",
                "",
                "Unknown ownership blocks release and must become a failure bundle.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "179.5-SOURCE-WIZARD-PARITY.md").write_text(
        "\n".join(
            [
                "# Phase 179.5 Source/Wizard Parity",
                "",
                "Containment defaults live in canonical Brainstack source:",
                "",
                "- `brainstack/product_contracts.py`",
                "- `scripts/run_rollback_matrix.py`",
                "- `scripts/write_hot_containment_artifacts.py`",
                "- `tests/test_hot_containment.py`",
                "",
                "No Docker-only, installed-Hermes-only, or manual container edit is accepted as completion.",
                "Wizard/runtime payload must consume these source contracts in later install phases.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    write_artifacts(Path(args.out_dir))
    print(f"WROTE {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
