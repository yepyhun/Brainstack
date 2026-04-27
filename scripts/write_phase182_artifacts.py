#!/usr/bin/env python3
"""Write Phase 182 presentation proof artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.product_contracts import (  # noqa: E402
    apply_presentation_hygiene,
    default_presentation_runtime_contract,
    dump_json,
    render_current_assignment_status,
)


def write_artifacts(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered = render_current_assignment_status(has_current_assignment_evidence=False, language="hu")
    cleaned, trace = apply_presentation_hygiene(
        "Hermes 😊\n" + rendered + "\nVan még kérdésed?",
        no_emoji=True,
        no_final_followup=True,
        decorative_prefixes=("Hermes",),
    )
    dump_json(
        out_dir / "182-PRESENTATION-PATH-PROOF.json",
        {
            "schema": "brainstack.phase182.presentation_path_proof.v1",
            "contract": default_presentation_runtime_contract(),
            "renderer_language": "hu",
            "final_text": cleaned,
        },
    )
    dump_json(out_dir / "182-STYLE-HYGIENE-TRACE.json", trace)
    (out_dir / "182-PERSONA-NEUTRALITY.md").write_text(
        "# Phase 182 Persona Neutrality\n\n- default personality: `neutral`\n- SOUL examples active prompt: `false`\n- decorative prefixes may be removed only when marked decorative by Hermes presentation metadata.\n",
        encoding="utf-8",
    )
    (out_dir / "182-HERMES-WIZARD-PATCH-PARITY.md").write_text(
        "# Phase 182 Hermes/Wizard Patch Parity\n\nPresentation defaults are source contracts in `brainstack/product_contracts.py`. Later wizard/install phases must consume these contracts; Docker-only or installed-Hermes-only edits are invalid.\n",
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
