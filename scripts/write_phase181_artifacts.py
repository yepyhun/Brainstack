#!/usr/bin/env python3
"""Write Phase 181 correction/provenance proof artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.product_contracts import (  # noqa: E402
    apply_corrected_false,
    audit_contamination_candidates,
    build_correction_proposal,
    build_phrase_provenance_report,
    dump_json,
)


def write_artifacts(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    claims = [{"claim_id": "a1", "source_role": "assistant", "claim_type": "assistant_self_claim"}]
    proposal = build_correction_proposal(
        source_event_id="u1",
        source_span_id="u1:s1",
        correction_type="reject_prior_assistant_self_claim",
        prior_claims=claims,
    )
    updated, receipts = apply_corrected_false(claims, proposal, corrected_at="2026-04-27T00:00:00Z")
    dump_json(
        out_dir / "181-CORRECTION-LINKS.json",
        {"schema": "brainstack.phase181.correction_links.v1", "proposal": proposal.to_dict(), "updated_claims": updated},
    )
    dump_json(
        out_dir / "181-PHRASE-PROVENANCE-REPORT.json",
        build_phrase_provenance_report(
            phrase="synthetic persona",
            timeline=[
                {
                    "turn_id": "t1",
                    "prompt_text": "normal prompt",
                    "provider_output": "synthetic persona",
                    "raw_transcript_stored": True,
                    "continuity_candidate": "assistant_self_claim",
                    "classification": "assistant_self_claim",
                    "firewall_decision": "dropped",
                }
            ],
        ),
    )
    audit = audit_contamination_candidates(
        [
            {
                "claim_id": "a2",
                "source_role": "assistant",
                "claim_type": "assistant_user_claim",
                "model_facing_default": True,
            }
        ]
    )
    (out_dir / "181-CONTAMINATION-AUDIT.md").write_text(
        "\n".join(
            [
                "# Phase 181 Contamination Audit",
                "",
                f"- suspect_count: `{audit['suspect_count']}`",
                "- raw_transcript_deleted: `false`",
                "- audit mode first; repair requires receipt.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    dump_json(
        out_dir / "181-REPAIR-RECEIPTS.json",
        {"schema": "brainstack.phase181.repair_receipts.v1", "receipts": receipts + audit["repair_receipts"]},
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
